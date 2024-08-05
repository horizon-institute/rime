#include <Windows.h>

#define PY_SSIZE_T_CLEAN

#ifdef _DEBUG
#undef _DEBUG
#include <Python.h>
#define _DEBUG
#else
#include <Python.h>
#endif


DWORD threadId = 0;
HANDLE hThread = nullptr;
HANDLE hExitMutex = nullptr;
FILE* logFile = nullptr;

struct NewPythonThreadStartupInfo
{
    const wchar_t* pythonInstallDir;
	void(*onStart)(void *);
	void *param;
};

static PyObject* PythonWriteImpl(PyObject* self, PyObject* args)
{
	const char *str = nullptr;
    Py_ssize_t len = 0;

	if (!PyArg_ParseTuple(args, "s#", &str, &len))
		return NULL;

    Py_BEGIN_ALLOW_THREADS

    if(logFile) {
        fwrite(str, 1, len, logFile);
    }

    Py_END_ALLOW_THREADS

	return PyLong_FromLong(0);
}

static PyMethodDef PythonWriteImplMethod = { "write", PythonWriteImpl, METH_VARARGS, "Write to debug output" };

static PyObject* PythonFlushImpl(PyObject* self, PyObject* args)
{
	OutputDebugString(L"PythonFlushImpl\n");
	return PyLong_FromLong(0);
}

static PyMethodDef PythonFlushImplMethod = { "flush", PythonFlushImpl, METH_VARARGS, "Flush debug output" };


const wchar_t *pythonZipSuffix = L"python312.zip";
const wchar_t *pythonExeSuffix = L"python.exe";

static DWORD WINAPI PythonThread(LPVOID lpParam)
{
	OutputDebugString(L"PythonThread\n");

    NewPythonThreadStartupInfo *info = (NewPythonThreadStartupInfo *)lpParam;

    // init Python
    OutputDebugString(L"Initializing Python...\n");

    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);

    config.home = (wchar_t *)info->pythonInstallDir;

    OutputDebugString(config.home);

#if 0
    size_t maxLen = wcslen(info->pythonInstallDir) + wcslen(pythonZipSuffix) + 2;
    auto pythonZip = new wchar_t[maxLen];

    swprintf_s(pythonZip, maxLen, L"%s\\%s", info->pythonInstallDir, pythonZipSuffix);
    PyConfig_SetString(&config, &config.pythonpath_env, pythonZip);

    delete[] pythonZip;

    auto pythonExePath = new wchar_t[wcslen(info->pythonInstallDir) + wcslen(pythonExeSuffix) + 2];
    swprintf_s(pythonExePath, wcslen(info->pythonInstallDir) + wcslen(pythonExeSuffix) + 2, L"%s\\%s", info->pythonInstallDir, pythonExeSuffix);
    PyConfig_SetString(&config, &config.executable, pythonExePath);
#endif


    Py_InitializeFromConfig(&config);

    // Ensure that we have sys.stdout and sys.stderr objects. These may not exist if running from a GUI.
    PyRun_SimpleString("class Std:\n"
        "    def isatty(self):\n"
        "        return False\n"
        "    def write(self, txt):\n"
        "        pass\n"
        "    def flush(self):\n"
        "        pass\n"
        "import sys\n"
        "sys.stdout = Std()\n"
        "sys.stderr = Std()\n"
    );

    if(PyErr_Occurred())
	{
		char error[2560];
		sprintf_s(error, "Setting stdout/stderr failed: %s\n", PyUnicode_AsUTF8(PyObject_Str(PyErr_Occurred())));
		OutputDebugStringA(error);
		PyErr_PrintEx(0);
	}

    PyObject* pyWrite = PyCFunction_NewEx(&PythonWriteImplMethod, NULL, NULL);

    auto pyStderr = PySys_GetObject("stderr");
    auto pyStdout = PySys_GetObject("stdout");

    PyObject_SetAttrString(pyStdout, "write", pyWrite);
    PyObject_SetAttrString(pyStderr, "write", pyWrite);

    if (PyErr_Occurred())
    {
        char error[2560];
        sprintf_s(error, "set attr error: %s\n", PyUnicode_AsUTF8(PyObject_Str(PyErr_Occurred())));
        OutputDebugStringA(error);
        PyErr_PrintEx(0);
    }

    // Set up the signal handler for SIGINT. The default handler in embedded Python is to ignore.
    PyRun_SimpleString("import signal\n"
        "def on_sigint(signal, frame):\n"
        "    raise KeyboardInterrupt\n"
        "signal.signal(signal.SIGINT, on_sigint)\n"
        );

    OutputDebugString(L"Python initialized. Running user code\n");

    // Run the user code.
    info->onStart(info->param);

    delete info;

    // Get the mutex
    WaitForSingleObject(hExitMutex, INFINITE);

    OutputDebugString(L"PythonThread exiting\n");

    Py_Finalize();

    // Signal to the main thread that we're done
    ReleaseMutex(hExitMutex);

	return 0;
}


void InitEmbedPython(const wchar_t *pythonInstallDir, void(*onStart)(void *), wchar_t *logFilename, void *param)
{
    NewPythonThreadStartupInfo* info = new NewPythonThreadStartupInfo();

	info->pythonInstallDir = pythonInstallDir;
    info->onStart = onStart;
    info->param = param;

    if (logFilename)
    {
        logFile = _wfsopen(logFilename, L"w", _SH_DENYNO);
    }

    hExitMutex = CreateMutex(NULL, TRUE, NULL);
    hThread = CreateThread(NULL, 0, PythonThread, (void *)info, 0, &threadId);
}

void StopEmbedPythonThread()
{
	OutputDebugString(L"Stopping Python thread...\n");

    // signal the thread to exit
    PyGILState_STATE gstate = PyGILState_Ensure();

    PyRun_SimpleString("import _thread\n"
		"_thread.interrupt_main()\n"
	);

    PyGILState_Release(gstate);

    // Signal to the Python thread that the GIL is released and it can exit
    ReleaseMutex(hExitMutex);

    // wait for the thread to exit
    OutputDebugString(L"Waiting for Python thread to exit...\n");
    WaitForSingleObject(hThread, INFINITE);
    OutputDebugString(L"Python thread exited.\n");

    CloseHandle(hThread);
    CloseHandle(hExitMutex);

    if(logFile) {
		fclose(logFile);
		logFile = nullptr;
	}
}