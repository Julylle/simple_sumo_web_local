from ctypes import cdll, c_int, c_char_p, CFUNCTYPE
import os
import platform
import sys
import logging

class SumoScheduler:
    def __init__(self, sumoPath=""):
        # Preparing some convenience member fields.
        self.version = 'Sumo24'
        self.platform_name = ''
        self.message_callback = None
        self.datacomm_callback = None
        self.scheduledJobs = 0
        self.install_path = "N/A"
        self._load_sumo(sumoPath)
        self.jobData = { }
        self.persistent = "persistent"
        self.VERSION = "24.0.0"
        
        if (self.getDLLVersion() != self.getPYVersion()):
            raise Exception(f"Version mismatch: sumoscheduler.py is version {self.getPYVersion()} but sumoscheduler.dll is {self.getDLLVersion()}")


    def _load_sumo(self, sumoPath=""):
        library_prefix = ''
        library_ext = ''
        self.platform_name = platform.system()
        if self.platform_name == 'Windows':
            library_ext = 'dll'
            library_prefix = ''
            import winreg

            def getInstallLocation():
                aKey = "SOFTWARE\\Dynamita\\" + self.version +"\\PATHS"
                aReg = winreg.ConnectRegistry(None,winreg.HKEY_LOCAL_MACHINE)
                try:
                    aKey = winreg.OpenKey(aReg, aKey)
                    val = winreg.QueryValueEx(aKey, "INST")
                    return val[0]
                except:
                    aKey = "SOFTWARE\\Dynamita\\" + self.version +"\\PATHS"
                    aReg = winreg.ConnectRegistry(None,winreg.HKEY_CURRENT_USER)
                    try:
                        aKey = winreg.OpenKey(aReg, aKey)
                        val = winreg.QueryValueEx(aKey, "INST")
                        return val[0]
                    except:
                        return ""

            if sumoPath == "":
                sumoPath = getInstallLocation()
            if sumoPath == "":
                raise FileNotFoundError(self.version + 'is not installed')
            if sys.version_info[0] > 3 or (sys.version_info[0] == 3 and sys.version_info[1] >= 8):
                os.add_dll_directory(sumoPath) # Python 3.8
        elif self.platform_name == 'Linux':
            library_ext = 'so'
            library_prefix = 'lib'
        elif self.platform_name == 'Darwin':
            library_ext = 'dylib'
            library_prefix = 'lib'
        else:
            raise NotImplementedError('Unsupported platform.')

        core_filename = os.path.join(
            sumoPath, library_prefix + "sumoscheduler." + library_ext
        )
        if os.path.isfile(core_filename):
            cwd = os.getcwd()
            os.chdir(sumoPath)
            self._scheduler = cdll.LoadLibrary(core_filename)
            os.chdir(cwd)
        else:
            raise FileNotFoundError('Core file not found: ' + core_filename)

        self.install_path = sumoPath

        self._scheduler.schedule.argtypes = [c_char_p, c_char_p, c_char_p, c_int]
        self._scheduler.schedule.restype = c_int
        self._scheduler.setParallelJobs.argtypes = [c_int]
        self._scheduler.setMaxJobReuse.argtypes = [c_int]
        self._scheduler.finish.argtypes = [c_int]
        self._scheduler.sendCommand.argtypes =[c_int, c_char_p]
        self._scheduler.setLogDetails.argtypes = [c_int]
        self._scheduler.getScheduledJobs.restype = c_int
        self._scheduler.getVersion.restype = c_int


        def convertToData(s):
            if (";" in s):
                result = []
                for item in s.split(";"):
                    result.append(convertToData(item))
                return result
            try:
                return float(s)
            except ValueError:
                return s


        def internal_datacomm_callback(job, msg):
            if self.datacomm_callback is not None and msg:
                data = {}
                lst = msg.decode('utf8').split("|")
                for pair in lst:
                    if not pair.strip():
                        continue
                    name, separator, value = pair.partition(" = ")
                    if not separator or not name.strip():
                        logging.warning("SUMO job %s: malformed data field %r", job, pair)
                        continue
                    data[name.strip()] = convertToData(value)
                if data:
                    self.datacomm_callback(job, data)
            return 0


        def internal_message_callback(job, msg):
            if (msg is not None) and (self.message_callback is not None):
                self.message_callback(job, msg.decode('utf8'))
            return 0;


        CALLBACKFUNC = CFUNCTYPE(c_int, c_int, c_char_p)
        self.c_message_callback = CALLBACKFUNC(internal_message_callback)
        self.c_datacomm_callback = CALLBACKFUNC(internal_datacomm_callback)

        self._scheduler.register_message_callback.argtypes = [CALLBACKFUNC]
        self._scheduler.register_message_callback(self.c_message_callback)
        self._scheduler.register_datacomm_callback.argtypes = [CALLBACKFUNC]
        self._scheduler.register_datacomm_callback(self.c_datacomm_callback)


    def schedule (self, model, commands, variables, blockDatacomm=False, jobData=None):
        varstr = "|".join(variables)
        id = self._scheduler.schedule(model.encode("utf8"), (";".join(commands)).encode("utf8"), varstr.encode("utf8"), int(blockDatacomm))
        self.jobData[id] = jobData
        self.scheduledJobs = self._scheduler.getScheduledJobs()
        return id

    def setParallelJobs(self, jobs):
        self._scheduler.setParallelJobs(jobs)


    def setMaxJobReuse(self, reuse):
        self._scheduler.setMaxJobReuse(reuse)


    def finish(self, job):
        self._scheduler.finish(job)
        if (self.jobData[job] == None or not (self.persistent in self.jobData[job]) or  self.jobData[job][self.persistent] != True):
            del self.jobData[job]
        self.scheduledJobs = self._scheduler.getScheduledJobs()

    def deleteJobData(self, job):
        del self.jobData[job]

    def sendCommand(self, job, command):
        self._scheduler.sendCommand(job, command.encode("utf8"))


    def getJobData(self, jobId):
        return self.jobData[jobId]


    def isSimFinishedMsg(self, msg):
        return msg.startswith("530004")


    def setLogDetails(self, level):
        self._scheduler.setLogDetails(level)
        
    def getPYVersion(self):
        return self.VERSION
    
    def getDLLVersion(self):
        v = self._scheduler.getVersion()
        b = v % 1000
        v = int(v/1000)
        m = v % 1000
        v = int(v/1000)
        return f"{v}.{m}.{b}"

    def cleanup(self):
        self.jobData.clear()
        self._scheduler.cleanup()


sumo = SumoScheduler()
