#include <Windows.h>
#include <string>
#include <optional>
#include <shellapi.h>
#include "PathCch.h"



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

    // We read launch.py and run it as a string so as to avoid passing FILE pointers from the launcher to the Python library.
    // This is because the Nuget version of the Python library we are using includes only a release build. Building
    // a debug build of the rest of the project results in FILE structures that are incompatible with the release build
    // and cause weird crashes deep inside msvcrt.
    fseek(fp, 0, SEEK_END);
    size_t size = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    char *buffer = new char[size + 1];
    fread(buffer, 1, size, fp);
    buffer[size] = 0;

    fclose(fp);

    PyRun_SimpleString(buffer);

    delete[] buffer;
}

static std::optional<std::wstring> getPythonDir()
{
    // Try to find the Python install dir as either below the executable or below the cwd.
     // 1. Try below the executable.
    wchar_t pythonInstallDir[MAX_PATH];

    GetModuleFileNameW(NULL, pythonInstallDir, MAX_PATH);
    PathCchRemoveFileSpec(pythonInstallDir, MAX_PATH);
    wcscat_s(pythonInstallDir, MAX_PATH, L"\\python");

    if (GetFileAttributesW(pythonInstallDir) == INVALID_FILE_ATTRIBUTES)
    {
        // 2. Try below the cwd.
        GetCurrentDirectoryW(MAX_PATH, pythonInstallDir);
        wcscat_s(pythonInstallDir, MAX_PATH, L"\\python");

        if (GetFileAttributesW(pythonInstallDir) == INVALID_FILE_ATTRIBUTES)
        {
            OutputDebugString(L"Python not found\n");
            return nullptr;
        }
    }

    return std::wstring(pythonInstallDir);
}

const wchar_t *launchPySuffix = L"launch.py";

void *StartRimeServer(void(*OnServerStartedFn)(void*), void* data)
{
    auto pythonInstallDir = getPythonDir();
    if (!pythonInstallDir.has_value())
	{
		return nullptr;
	}

    size_t maxLen = pythonInstallDir->size() + wcslen(launchPySuffix) + 2;
    auto launchPy = new wchar_t[maxLen];

    swprintf_s(launchPy, maxLen, L"%s\\%s", pythonInstallDir->c_str(), launchPySuffix);

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

    InitEmbedPython(pythonInstallDir.value(), OnPythonThreadStarted, LogPath, onRimeServerStarted);

    return onRimeServerStarted;
}

void StopRimeServer(void *handle)
{
    auto onRimeServerStarted = (OnRimeServerStartedStruct *)handle;

	StopEmbedPythonThread();

    delete[] onRimeServerStarted->launchPy;
    delete onRimeServerStarted;
}