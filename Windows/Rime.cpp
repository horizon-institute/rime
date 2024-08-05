// Rime.cpp : Defines the entry point for the application.
//

#include "framework.h"
#include "Rime.h"
#include "Splash.h"
#include "RimePython.h"
#include "delayimp.h"
#include "Shlwapi.h"
#include "PathCch.h"

#include <shellapi.h>



#define MAX_LOADSTRING 100

// Global Variables:
HINSTANCE hInst;                                // current instance
WCHAR szTitle[MAX_LOADSTRING];                  // The title bar text
WCHAR szWindowClass[MAX_LOADSTRING];            // the main window class name
Splash *splash;
HWND hWndMain;
HFONT hFont;
void *rimeServerHandle;

static const bool showSplash = true;

// Forward declarations of functions included in this code module:
ATOM                MyRegisterClass(HINSTANCE hInstance);
BOOL                InitInstance(HINSTANCE, int);
LRESULT CALLBACK    WndProc(HWND, UINT, WPARAM, LPARAM);
INT_PTR CALLBACK    About(HWND, UINT, WPARAM, LPARAM);

int APIENTRY wWinMain(_In_ HINSTANCE hInstance,
                     _In_opt_ HINSTANCE hPrevInstance,
                     _In_ LPWSTR    lpCmdLine,
                     _In_ int       nCmdShow)
{
    UNREFERENCED_PARAMETER(hPrevInstance);
    UNREFERENCED_PARAMETER(lpCmdLine);

    splash = nullptr;

    // Initialize global strings
    LoadStringW(hInstance, IDS_APP_TITLE, szTitle, MAX_LOADSTRING);
    LoadStringW(hInstance, IDC_RIME, szWindowClass, MAX_LOADSTRING);
    MyRegisterClass(hInstance);

    // Perform application initialization:
    if (!InitInstance (hInstance, nCmdShow))
    {
        return FALSE;
    }

    HACCEL hAccelTable = LoadAccelerators(hInstance, MAKEINTRESOURCE(IDC_RIME));

    MSG msg;

    // Main message loop:
    while (GetMessage(&msg, nullptr, 0, 0))
    {
        if (!TranslateAccelerator(msg.hwnd, hAccelTable, &msg))
        {
            TranslateMessage(&msg);
            DispatchMessage(&msg);
        }
    }

    return (int) msg.wParam;
}



//
//  FUNCTION: MyRegisterClass()
//
//  PURPOSE: Registers the window class.
//
ATOM MyRegisterClass(HINSTANCE hInstance)
{
    WNDCLASSEXW wcex;

    wcex.cbSize = sizeof(WNDCLASSEX);

    wcex.style          = CS_HREDRAW | CS_VREDRAW;
    wcex.lpfnWndProc    = WndProc;
    wcex.cbClsExtra     = 0;
    wcex.cbWndExtra     = 0;
    wcex.hInstance      = hInstance;
    wcex.hIcon          = LoadIcon(hInstance, MAKEINTRESOURCE(IDI_RIME));
    wcex.hCursor        = LoadCursor(nullptr, IDC_ARROW);
    wcex.hbrBackground  = (HBRUSH)(COLOR_WINDOW+1);
    wcex.lpszMenuName = 0; // MAKEINTRESOURCEW(IDC_RIME);
    wcex.lpszClassName  = szWindowClass;
    wcex.hIconSm        = LoadIcon(wcex.hInstance, MAKEINTRESOURCE(IDI_SMALL));

    return RegisterClassExW(&wcex);
}

void RimeServerStarted(void *data) {
    HWND hWnd = (HWND)data;

    // Running on a separate thread, so post a message to the wndproc to hide the splash screen.
    PostMessage(hWnd, WM_TIMER, 0, 0);
}

BOOL InitInstance(HINSTANCE hInstance, int nCmdShow)
{
    hInst = hInstance; // Store instance handle in our global variable

    HFONT hFont = CreateFont(20, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, ANSI_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Arial");

    hWndMain = CreateWindowW(szWindowClass, szTitle, WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        CW_USEDEFAULT, 0, 600, 100, nullptr, nullptr, hInstance, nullptr);

    if (!hWndMain)
    {
        return FALSE;
    }

    if (showSplash) {
        splash = new Splash(hInstance, nCmdShow);
        splash->Show();
    }

    rimeServerHandle = StartRimeServer(RimeServerStarted, hWndMain);
  
    // ShowWindow(hWndMain, nCmdShow);
    UpdateWindow(hWndMain);

    // Set a timer to hide the splash screen even if RIME fails to load.
    SetTimer(hWndMain, 1, 60000, NULL);

    return TRUE;
}

//
//  FUNCTION: WndProc(HWND, UINT, WPARAM, LPARAM)
//
//  PURPOSE: Processes messages for the main window.
//
//  WM_COMMAND  - process the application menu
//  WM_PAINT    - Paint the main window
//  WM_DESTROY  - post a quit message and return
//
//
LRESULT CALLBACK WndProc(HWND hWnd, UINT message, WPARAM wParam, LPARAM lParam)
{
    switch (message)
    {
    case WM_COMMAND:
        {
            int wmId = LOWORD(wParam);
            // Parse the menu selections:
            switch (wmId)
            {
            case IDM_ABOUT:
                DialogBox(hInst, MAKEINTRESOURCE(IDD_ABOUTBOX), hWnd, About);
                break;
            case IDM_EXIT:
                DestroyWindow(hWnd);
                break;
            default:
                return DefWindowProc(hWnd, message, wParam, lParam);
            }
        }
        break;
    case WM_PAINT:
        {
            PAINTSTRUCT ps;
            HDC hdc = BeginPaint(hWnd, &ps);

            // Draw text
            RECT rc;
            GetClientRect(hWnd, &rc);
            SelectObject(hdc, hFont);
            rc.left += 5;
            rc.top += 5;
            DrawText(hdc, L"RIME is running! Visit http://localhost:3000 in your browser.", -1, &rc, DT_LEFT);

            // clean up
            EndPaint(hWnd, &ps);
        }
        break;
    case WM_TIMER:
        if(splash)
            splash->Hide();
        KillTimer(hWnd, 1);
        OutputDebugString(L"Timer expired\n");
        ShowWindow(hWnd, SW_SHOW);
        ShellExecute(NULL, L"open", L"http://localhost:3000/", NULL, NULL, SW_SHOWNORMAL);
        // StopRimeServer(rimeServerHandle);
        break;
    case WM_DESTROY:
        delete splash;
        OutputDebugString(L"Exiting\n");
        StopRimeServer(rimeServerHandle);

        DeleteObject(hFont);
        PostQuitMessage(0);
        break;
    default:
        return DefWindowProc(hWnd, message, wParam, lParam);
    }
    return 0;
}

// Message handler for about box.
INT_PTR CALLBACK About(HWND hDlg, UINT message, WPARAM wParam, LPARAM lParam)
{
    UNREFERENCED_PARAMETER(lParam);
    switch (message)
    {
    case WM_INITDIALOG:
        return (INT_PTR)TRUE;

    case WM_COMMAND:
        if (LOWORD(wParam) == IDOK || LOWORD(wParam) == IDCANCEL)
        {
            EndDialog(hDlg, LOWORD(wParam));
            return (INT_PTR)TRUE;
        }
        break;
    }
    return (INT_PTR)FALSE;
}

// Load Python library
#pragma comment(lib, "Shlwapi.lib")
#pragma comment(lib, "Pathcch.lib")
HMODULE LoadPythonLibrary(const char *szDll)
{
    // Load Python from the python\ directory either below the executable or below the cwd.
    wchar_t szPath[MAX_PATH];

    // First try exe dir + python\libname.dll
    GetModuleFileNameW(nullptr, szPath, MAX_PATH);
    PathCchRemoveFileSpec(szPath, MAX_PATH);

    wcscat_s(szPath, MAX_PATH, L"\\python\\");

    wchar_t szDllPath[MAX_PATH];
    mbstowcs_s(nullptr, szDllPath, szDll, MAX_PATH);

    wcscat_s(szPath, MAX_PATH, szDllPath);

	HMODULE hModule = LoadLibrary(szPath);
    if (hModule != nullptr) {
        return hModule;
    }

    // Couldn't find it relative to the exe, so try cwd + python\libname.dll
    GetCurrentDirectoryW(MAX_PATH, szPath);
    wcscat_s(szPath, MAX_PATH, L"\\python\\");
    wcscat_s(szPath, MAX_PATH, szDllPath);

    hModule = LoadLibrary(szPath);
    if (hModule != nullptr) {
		return hModule;
	}

    OutputDebugString(L"Failed to load Python library, falling back to regular search path\n");
    return nullptr;
}

// Delay load DLL handler so we can provide a custom path for Python
FARPROC WINAPI DelayLoadHandler(unsigned dliNotify, PDelayLoadInfo pdli)
{
    if (dliNotify == dliNotePreLoadLibrary) {
        if (CompareStringA(LOCALE_SYSTEM_DEFAULT, NORM_IGNORECASE, pdli->szDll, -1, "python3.dll", -1) == CSTR_EQUAL
            || CompareStringA(LOCALE_SYSTEM_DEFAULT, NORM_IGNORECASE, pdli->szDll, -1, "python312.dll", -1) == CSTR_EQUAL) {
            return (FARPROC)LoadPythonLibrary(pdli->szDll);
        }
    }
	return NULL;
}

ExternC const PfnDliHook __pfnDliNotifyHook2 = DelayLoadHandler;
ExternC const PfnDliHook __pfnDliFailureHook2 = DelayLoadHandler;
