#include <Windows.h>

#define PY_SSIZE_T_CLEAN

#ifdef _DEBUG
#undef _DEBUG
#include <Python.h>
#define _DEBUG
#else
#include <Python.h>
#endif

#include "EmbedPython.h"
#include "RimePython.h"

#include "shlobj_core.h"

DWORD serverCheckThreadId = 0;
HANDLE hServerCheckThread = NULL;

struct OnRimeServerStartedStruct {
    void(*OnServerStarted)(void*);
	void* data;
    wchar_t *launchPy;
};


static const char *CheckRimeServerRunning = R"(
import urllib.request
import time

# Start a thread to report back to the embedding system when the app is actually available.

def _report_when_available():
    too_slow = time.time() + 30
    
    while time.time() < too_slow:
        try:
            req = urllib.request.urlopen('http://localhost:3000/')
            if req.status < 400:
                return
        except:
            pass
        time.sleep(0.5)

    raise Exception("Server did not start in time")

_report_when_available();
)";

static DWORD WINAPI CheckRimeServerRunningThread(LPVOID lpParam)
{
    auto onRimeServerStarted = (OnRimeServerStartedStruct *)lpParam;

    PyGILState_STATE gstate = PyGILState_Ensure();

    PyRun_SimpleString(CheckRimeServerRunning);

    PyGILState_Release(gstate);

    OutputDebugString(L"CheckRimeServerRunningThread done\n");
    onRimeServerStarted->OnServerStarted(onRimeServerStarted->data);

	return 0;
}


static void OnPythonThreadStarted(void *data)
{
    auto onRimeServerStarted = (OnRimeServerStartedStruct *)data;

    // Start a thread to check if the server is running.
    hServerCheckThread = CreateThread(NULL, 0, CheckRimeServerRunningThread, data, 0, &serverCheckThreadId);

    FILE* fp;
    auto err = _wfopen_s(&fp, onRimeServerStarted->launchPy, L"rb");
    if (fp == NULL)
	{
		OutputDebugString(L"Failed to open launch.py\n");
		return;
	}

    PyRun_SimpleFileEx(fp, "launch.py", 1);
}

const wchar_t *launchPySuffix = L"launch.py";

void *StartRimeServer(void(*OnServerStartedFn)(void*), void* data)
{
    auto pythonInstallDir = L"C:\\Users\\wzddm\\source\\rime-release-test\\rime-windows\\python";

    size_t maxLen = wcslen(pythonInstallDir) + wcslen(launchPySuffix) + 2;
    auto launchPy = new wchar_t[maxLen];

    swprintf_s(launchPy, maxLen, L"%s\\%s", pythonInstallDir, launchPySuffix);

    OnRimeServerStartedStruct* onRimeServerStarted = new OnRimeServerStartedStruct();
    onRimeServerStarted->OnServerStarted = OnServerStartedFn;
    onRimeServerStarted->data = data;
    onRimeServerStarted->launchPy = launchPy;

    // Choose a logfile location in AppData\Local\Rime, creating the directory if it doesn't exist.
    WCHAR LogPath[MAX_PATH];
    SHGetFolderPathW(NULL, CSIDL_LOCAL_APPDATA, NULL, 0, LogPath);
    wcscat_s(LogPath, MAX_PATH, L"\\Rime");
    CreateDirectoryW(LogPath, NULL);
    wcscat_s(LogPath, MAX_PATH, L"\\rime.log");

    InitEmbedPython(pythonInstallDir, OnPythonThreadStarted, LogPath, onRimeServerStarted);

    return onRimeServerStarted;
}

void StopRimeServer(void *handle)
{
    auto onRimeServerStarted = (OnRimeServerStartedStruct *)handle;

	StopEmbedPythonThread();

    delete[] onRimeServerStarted->launchPy;
    delete onRimeServerStarted;
}