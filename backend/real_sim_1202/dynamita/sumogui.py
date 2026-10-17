import dynamita.dmqclient as DMQ
import dynamita.tool as dtool
import time
import subprocess

class SumoGUI:
    def __init__(self, project: str):
        self.model_initialized = False
        self.project_loaded = False
        self.dmq = DMQ.DMQ.create()
        self.last_message = ""
        self.project_path = ""
        self.CommunicationFrequency = 0.2
        print(f"printingkey,{self.dmq.key}<")
        print(project)
        print(f'{DMQ.DMQ.sumo_path}/{DMQ.DMQ.version} {self.dmq.key}')
        self.process = subprocess.Popen([f"{DMQ.DMQ.sumo_path}/{DMQ.DMQ.version}.exe", project, "-dmq", self.dmq.key])
        
    def communicate(self):
        line = self.dmq.read_data(False)
        
        if (line == "CLOSED"):
            self.last_message = "CLOSED"
            return False
            
        if (line != ""):
            dtool.log_print(f"SumoGUI: {line}")
            self.last_message = line
        else:
            return False
        if line.startswith("project_init "):
            self.project_path = line.replace("project_init ", "")
        elif (line == "project_loaded"):
            self.project_loaded = True
        elif (line == "model_init"):
            self.model_initialized = True
        elif (line == "model_unloaded"):
            self.model_initialized = False
            
        return True
        
    def wait_for(self, l):
        while not l():
            if not self.communicate():
                time.sleep(self.CommunicationFrequency)   

    def set_variable(self, variable : str, value):
        self.dmq.send_data(f"core_cmd set {variable} {value};")
        
    def set_variables(self, data):
        if len(data) > 0:
            s = ""
            for y in data:
                x = data[y]
                s = f'{s}core_cmd set {y} {x};\n'
            self.dmq.send_data(s)
    
    def onstart(self, command : str):
        self.dmq.send_data(f"onstart {command};")
        
    def push_button(self, tab : str, button : str, param : str = ""):
        if (param == ""):
            self.dmq.send_data(f"button {tab} {button}")
        else:
            self.dmq.send_data(f"button {tab} {button} {param}")
        
    def select_maintab(self, tab : str):
        self.dmq.send_data(f"maintab {tab}")
        
    def core_command(self, command : str):
        self.dmq.send_data(f"core_cmd {command};")
        
    def _starts_with_coremsg_any(self, msg : str, prefixes : list):
        for p in prefixes:
            if msg.startswith("core_msg " + p):
                return True
        return False
    
    def is_running(self):
        return self.process.poll() is None
        
    def core_command_sync(self, command : str, response):
        if type(response) is list:
            pass
        else:
            response = [response]
        self.last_message = ""
        self.core_command(command)                
        self.wait_for(lambda: not self.is_running() or self._starts_with_coremsg_any(self.last_message, response))
                
    #def close(self):
    #    self.dmq.close()

    def close(self):
        try:
            # 尝试通过 DMQ 向 Sumo 发送退出命令
            self.dmq.send_data("exit")
            # 等待 Sumo 进程优雅退出（这里设置等待超时为 5 秒，可根据需要调整）
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # 如果等待超时，则强制终止进程
            self.process.kill()
        finally:
            # 如有需要，清理 DMQ 连接
            if hasattr(self.dmq, "close"):
                self.dmq.close()
