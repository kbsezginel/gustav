import os
import json
import time
import shutil
import subprocess
from datetime import datetime

import psutil
import pkgutil

from tools import read_json

from gustav.utils import exp as gustav_exp
from gustav.user_scripts import html as html_scripts


class GustavIO(object):
    """Gustav IO"""
    def __init__(self, server_pid, subject_id="1", port=5050, experiment='', local=False):
        """
        Initialize gustav input/output.
        """
        self.server_pid = server_pid
        self.root = 'static'
        self.out_dir = 'exp'
        self.sessions = {}
        self.num_trial = 0
        self.port = port
        self.max_ports = 10
        self.base_port = 5050
        self.id = subject_id
        self.scripts = []
        # Read experiments as submodule
        # Check the experiment script if the experiment is available (exp.ready = True)
        # self.experiment = 'gustav_exp__adaptive_quietthresholds'
        # self.script = f'{self.experiment}.py'
        file_dir = os.path.dirname(os.path.abspath(__file__))
        # script_dir = os.path.join(file_dir, '..', 'gustav', 'user_scripts', 'html')
        # self.script_dir = os.path.abspath(script_dir)
        self.process = None
        self.dir = None
        self.str_time = None
        self.running_file = os.path.join(file_dir, 'running.json')
        # if self.port == self.base_port and os.path.exists(self.running_file):
        #     print(f'Removing {self.running_file}')
        #     os.remove(self.running_file)
        self.update_running()
        if local:
            self.url = 'http://0.0.0.0'
        else:
            self.url = 'http://74.109.252.140'
        self.experiments = []

    def setup_script(self, script):
        self.script = script
        file_dir = os.path.dirname(os.path.abspath(__file__))
        script_dir = os.path.join(file_dir, '..', 'gustav', 'user_scripts', 'html')
        self.script_dir = os.path.abspath(script_dir)

    def __repr__(self):
        if self.process is None:
            pid = None
        else:
            pid = self.process.pid
        return f"Gustav IO\n  Server PID: {self.server_pid} Port: {self.port}\n  ID: {self.id}\n  Gustav PID: {pid}\n  Directory: {self.dir}"

    def setup(self, subject_id, port):
        """
        Set up subject id and port.
        Create subject directory (deletes if it exists)
        """
        self.id = subject_id
        self.port = port
        self.port_dir = os.path.join(self.root, self.out_dir, str(self.port))
        os.makedirs(self.port_dir, exist_ok=True)
        self.subject_dir = os.path.join(self.port_dir, str(self.id))
        self.dir = os.path.join(self.port_dir, str(self.id))
        if os.path.exists(self.dir):
            self.abort(data, keep_dir=False)
        os.makedirs(self.dir)

    def read(self, data):
        self.id = data['id']
        self.dir = os.path.join(self.port_dir, str(self.id))
        if self.id not in self.sessions:
            self.sessions[self.id] = {'id': self.id, 'dir': self.dir, 'trial': self.num_trial}
        else:
            self.sessions[self.id] = {**data, **self.sessions[self.id]}
        self.ses = self.sessions[self.id]
        print(self)

    def run(self, sleep=3):
        cmd = ['python', '-u', self.script, '-s', f'{self.id}:{self.port}']
        # redirect output to a file in subject dir
        self.process_out = os.path.join(self.dir, 'out.txt')
        self.process = subprocess.Popen(cmd, cwd=self.script_dir, stdout=open(self.process_out, 'w'))
        self.process_start_time = datetime.now()
        self.str_time = self.process_start_time.strftime("%m/%d/%Y, %H:%M:%S")
        print(f'Running script: {self.script} | PID: {self.process.pid}')
        new_run = {'pid': self.process.pid,
                   'port': self.port,
                   'script': self.script,
                   'time': self.str_time,
                   'sid': self.id}
        self.update_running(append=new_run)
        time.sleep(sleep)

    def update_running(self, append=None, remove=None):
        pids = self.get_processes(verbose=False)
        if not os.path.exists(self.running_file):
            self.running = []
            with open(self.running_file, 'w') as f:
                json.dump({'ports': {self.port: self.server_pid}, 'subjects': []}, f)
        else:
            with open(self.running_file, 'r') as f:
                self.running = json.load(f)
            running = {'ports': {}, 'subjects': []}

            for p in self.running['ports']:
                if int(self.running['ports'][p]) in pids:
                    running['ports'][int(p)] = int(self.running['ports'][p])

            for s in self.running['subjects']:
                if int(s['pid']) in pids:
                    running['subjects'].append(s)
            self.running = running

            self.running['ports'][self.port] = self.server_pid
            if append is not None:
                self.running['subjects'].append(append)
            if remove is not None:
                self.running['subjects'] = [r for r in self.running['subjects'] if r['pid'] != remove['pid']]
            with open(self.running_file, 'w') as f:
                json.dump(self.running, f)

    def is_running(self):
        if self.process is None:
            return False
        else:
            poll = self.process.poll()
            if poll is None:
                return True
            else:
                return False

    def kill(self, pid=None):
        """
        Kill Gustav process
        """
        if pid is None:
            pid = self.process.pid
            self.process.kill()
        print(f'Killing gustav script pid: {pid}')
        out = subprocess.run(f'kill {pid}', shell=True, capture_output=True, text=True)
        self.update_running(remove={'pid': pid})
        if out.returncode != 0:
            print(f'Process {pid} does not exist : ', out.stderr)
            return False
        else:
            print(f'Process {pid} killed')
            return True

    def send_request(self, data):
        """
        Send request to gustav.
        """
        print(f"send_request: {data}")
        self.read(data)
        self.request = data
        self.response = data
        if data['type'] == 'answer':
            request_type = 'trial'
            self.num_trial += 1
        else:
            request_type = data['type']
        if not hasattr(self, 'id'):
            print('WARNING: No subject id available, skipping')
        else:
            self.expected_response = os.path.join(self.dir, f"g{self.num_trial}_{request_type}.json")
            data['response_file'] = self.expected_response
            self.dump(data=data, prefix='c')

    def get_response(self, sleep=0.1, max_timeout=20, max_load_attempts=3):
        """
        Get response from gustav.
        """
        print(f'Waiting for response: {self.expected_response}')
        timeout = 0
        load_attempt = 0
        while not os.path.exists(self.expected_response) and timeout <= max_timeout:
            time.sleep(sleep)
            timeout += sleep
            # print(f"waiting {timeout} < {max_timeout}")
        if timeout <= max_timeout:
            print(f"Received reponse")
            for i in range(max_load_attempts):
                try:
                    self.response = self.load(self.expected_response)
                except:
                    load_attempt += 1
                    print(f'Could not load file, attempt: {load_attempt}/{max_load_attempts}')
                    time.sleep(sleep)
            if load_attempt >= max_load_attempts:
                print(f'Reached max load attempts: {max_load_attempts}, ignoring out')
                self.response = {}
        else:
            print(f'Max timeout ({max_timeout} s) reached, no response!')
            self.response = {}
        return self.response

    def initialize(self, data):
        self.read(data)
        self.num_trial = 0
        self.response = read_json("static/style.json")
        self.style = read_json("static/style.json")
        print('initialize' + '-' * 30 + f'\n{self}')

    def login(self, data):
        print(f'Login: {data}')
        if not os.path.exists('pwd.json'):
            pwds = self.load('pwd_test.json')
        else:
            pwds = self.load('pwd.json')
        response = 'false'
        for pwd in pwds:
            if data['username'] == pwd['username'] and data['password'] == pwd['password']:
                response = 'true'
        return response

    def read_experiments(self, available_ports=[], url=None, name=None):
        """
        Read all available experiment from gustav.user_scripts.html
        """
        experiments = []
        for html_exp in pkgutil.iter_modules(html_scripts.__path__):
            submodule = f'gustav.user_scripts.html.{html_exp.name}'
            exp_title = html_exp.name.replace('gustav_exp__', '').replace('_', '\n')
            exp = {'title': exp_title,
                   'description': '',
                   'url': '', 'ready': False, 'name': html_exp.name}
            try:
                exp_script = __import__(submodule, fromlist=[None])
                if hasattr(exp_script, 'setup'):
                    exp_script.setup(gustav_exp)
                    exp['title'] = gustav_exp.title
                    exp['description'] = gustav_exp.note
                    # template = exp_script.theForm.Interface.__module__.split('.')[-1]
                    if len(available_ports) > 0:
                        port = min(available_ports)
                        print(f'{len(available_ports)} ports available, selected {port}')
                        available_ports.remove(port)
                        exp['url'] = f'{self.url}:{port}/{gustav_exp.url}-{html_exp.name}'
                        print('---> url: ', exp['url'])
                        exp['ready'] = True
                    else:
                        print('No ports available!')
                else:
                    exp['description'] = 'Experiment has no setup function'
            except Exception as e:
                exp['description'] = f'Failed to load experiment: {e}'
                exp['url'] = ''
                exp['ready'] = False
            if url is None and name is None:
                experiments.append(exp)
            else:
                if url == gustav_exp.url and name == html_exp.name:
                    experiments.append(exp)
        return experiments

    def get_experiments(self):
        # Get running processes
        procs = self.get_processes()
        # Kill if no activity

        # Get running servers
        self.update_running()
        exp_ports = [int(p) for p in self.running['ports'] if int(p) != self.base_port]
        print(f'Exp ports: {exp_ports}')
        port_pids = self.running['ports'].values()
        print(f'Port pids: {port_pids}')
        print(f'procs: {procs}')
        running_ports = [pt for pt, pd in self.running['ports'].items() if pd in port_pids]
        print(f'Running ports: {running_ports} Total processes: {len(procs)}')
        # Check ifthe gustav process are running
        used_ports = [s['port'] for s in self.running['subjects'] if int(s['pid']) in procs]
        print(f'Used ports: {used_ports}')
        available_ports = [p for p in exp_ports if p not in used_ports and p in running_ports]
        print(f'Avail ports: {available_ports}')

        self.experiments = self.read_experiments(available_ports)
        print('get_experiments' + '-' * 30 + f'\n{self.experiments}')
        return {'experiments': self.experiments}

    def get_setup(self):
        self.update_running()
        procs = self.get_processes()
        exp_ports = [p for p in self.running['ports'] if int(p) != self.base_port]
        port_pids = self.running['ports'].values()
        running_ports = [pt for pt, pd in self.running['ports'].items() if pd in port_pids]
        used_ports = [s['port'] for s in self.running['subjects'] if int(s['pid']) in procs]
        available_ports = [p for p in exp_ports if p not in used_ports and p in running_ports]

        all_ports = sorted([int(p) for p in self.running['ports']])
        port_info = []
        for port in all_ports:
            pid = self.running['ports'][port]
            if port in used_ports:
                status = 'Busy'
            elif port in available_ports:
                status = 'Ready'
            elif port == self.base_port:
                status = 'Base Port'
            else:
                status = 'Unknown'
            port_info.append({'port': f'{port} : {status}', 'id': f'PID: {pid}'})
        exps = [{'title': 'Running ports', 'description': f'{len(port_info)} port(s)', 'subjects': port_info}]

        for exp in self.get_experiments()['experiments']:
            sbj = []
            for r in self.running['subjects']:
                sbj.append({'id': r['sid'], 'port': r['port'], 'time': r['time']})
            e = {'title': exp['title'], 'description': f'{len(sbj)} subject(s)', 'subjects': sbj}
            exps.append(e)

        data = {'experiments': exps,
                'max_ports': self.max_ports,
                'base_port': self.base_port,
                }
        print('get_setup' + '-' * 30 + f'\n{self}')
        print(data)
        return data

    def dump(self, data=None, filename=None, prefix='', suffix=''):
        """Dump data to json file"""
        if data is None:
            data = self.response
        if filename is None:
            filename = os.path.join(self.dir, f"{prefix}{self.num_trial}_{data['type']}{suffix}.json")
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f'dump -> {filename}')

    def load(self, filename):
        """Load json file"""
        with open(filename, "r") as f:
            data = json.load(f)
        return data

    def get_processes(self, name='python', status=['running', 'sleeping'], verbose=True):
        procs = []
        for proc in psutil.process_iter():
            try:
                # Get process name & pid from process object.
                processName = proc.name()
                processID = proc.pid
                # TODO: Parse time
                processTime = proc.create_time()
                # Filter according to status
                processStatus = proc.status()
                if name in processName and processStatus in status:
                    if verbose:
                        print(f'{processName} {processID} {processStatus} {processTime}')
                    procs.append(processID)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return procs
