import os
import json
import time
import shutil
import subprocess

from tools import select_audio, read_json


class Experiment(object):
    """Psylab Experiment"""
    def __init__(self, subject_id="1", port=5050):
        self.root = 'static'
        self.out_dir = 'exp'
        self.sessions = {}
        self.num_trial = 0
        self.port = port
        self.id = subject_id
        self.script = 'gustav_exp__web_adaptive_quietthresholds.py'
        file_dir = os.path.dirname(os.path.abspath(__file__))
        script_dir = os.path.join(file_dir, '..', 'gustav', 'user_scripts')
        self.script_dir = os.path.abspath(script_dir)
        self.process = None

    def __repr__(self):
        return f"Psylab experiment\n  Port: {self.port}\n  ID: {self.id}\n  Trial: {self.num_trial}\n  Directory: {self.dir}\n  Sessions: {len(self.sessions)}"

    def setup(self, subject_id="1", port=5050):
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
        print(f'Running script: {self.script} | PID: {self.process.pid}')
        time.sleep(sleep)

    def is_running(self):
        if self.process is None:
            return False
        else:
            poll = self.process.poll()
            if poll is None:
                return True
            else:
                return False

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
        # if os.path.exists(self.dir):
        #     self.abort(data, keep_dir=False)
        # os.makedirs(self.dir)
        self.num_trial = 0
        self.response = read_json("static/style.json")
        self.style = read_json("static/style.json")
        print('initialize' + '-' * 30 + f'\n{self}')

    def abort(self, data, keep_dir=True):
        self.read(data)
        if os.path.exists(self.dir):
            print('Session exists! Deleting...')
            if len(os.listdir(self.dir)) > 1:
                for f in os.listdir(self.dir):
                    os.remove(os.path.join(self.dir, f))
            if not keep_dir:
                shutil.rmtree(self.dir)
        output = {
            'type': 'abort',
            'message': "Experiment has been aborted."
        }
        self.response = output
        self.num_trial = 0
        print('abort' + '-' * 30 + f'\n{self}')

    def trial(self, data):
        self.read(data)
        self.num_trial += 1
        # Ask gustav for audio files
        # For testing stop the experiment after 3 trials
        if self.num_trial >= 5:
            self.stop(data)
        else:
            if 'answer' in data:
                if data['answer'] == "1":
                    self.freq1 += 200
                    self.freq2 += 200
                else:
                    self.freq1 -= 200
                    self.freq2 -= 200
            files = select_audio(self.freq1, self.freq2)
            print("Frequency 1: {self.freq1} | 2: {self.freq2}")
            names = [i.split('/')[-1].split('.')[0] for i in files]
            audio = []
            for i, (f, n) in enumerate(zip(files, names), start=1):
                audio.append({'name': i, 'file': f, 'id': i})
            output = {
                        'type': 'trial',
                        'lower_left_text': 'Trial: {}'.format(self.num_trial),
                        'lower_right_text': f'Session ID: {self.id}',
                        'upper_left_text': 'Psylab n-AFC Experiment | Quiet Thresholds',
                        'items': audio,
                        'prompt1': 'Press space to listen',
                        'prompt2': 'Select a sound (press 1 or 2)',
                        'answer': 1,
                        'delay': 500,
                        'next_delay': 2000,
                      }
            self.response = output
            print('trial' + '-' * 30 + f'\n{self}')

    def stop(self, data):
        self.read(data)
        output = {
          "type": "stop",
          "message" : "Experiment completed, thank you for participating"
        }
        self.response = output
        print('stop' + '-' * 30 + f'\n{self}')

    def info(self, data):
        self.read(data)
        output = {
          "type": "info",
          "message": "n-AFC Experiment | Quiet Thresholds"
        }
        self.response = output
        print('info' + '-' * 30 + f'\n{self}')

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
