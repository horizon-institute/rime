/* Splash screen consisting of a single bitmap */

#include <windows.h>
#include <WinUser.h>
#include "Resource.h"
#include "Splash.h"

Splash *g_pSplash;
BITMAP bm;

const int padding = 20;

// window proc for splash screen
LRESULT CALLBACK SplashWndProc(HWND hWnd, UINT message, WPARAM wParam, LPARAM lParam)
{
	switch (message)
	{
	case WM_PAINT:
	{
		PAINTSTRUCT ps;
		HDC hdc = BeginPaint(hWnd, &ps);
		// draw the bitmap
		HDC hdcMem = CreateCompatibleDC(hdc);
		SelectObject(hdcMem, g_pSplash->hBitmap);
		BitBlt(hdc, padding, padding, bm.bmWidth, bm.bmHeight, hdcMem, 0, 0, SRCCOPY);
		DeleteDC(hdcMem);

		EndPaint(hWnd, &ps);
		break;
	}
	case WM_DESTROY:
	{
		PostQuitMessage(0);
		break;
	}
	default:
		return DefWindowProc(hWnd, message, wParam, lParam);
	}
	return 0;
}


Splash::Splash(HINSTANCE hInstance, int nCmdShow)
{
	// Set the global pointer
	g_pSplash = this;

	// Load the bitmap as a handle with transparency
	hBitmap = LoadImage(hInstance, MAKEINTRESOURCE(IDB_SPLASHIMAGE), IMAGE_BITMAP, 0, 0, LR_CREATEDIBSECTION | LR_LOADTRANSPARENT | LR_LOADMAP3DCOLORS);

	// Get the bitmap's dimensions
	GetObject(hBitmap, sizeof(bm), &bm);

	// Register the window class
	WNDCLASS wc = { 0 };
	wc.lpszClassName = L"Splash";
	wc.hInstance = hInstance;
	wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
	wc.lpfnWndProc = SplashWndProc;
	wc.hCursor = LoadCursor(NULL, IDC_ARROW);
	RegisterClass(&wc);

	// Create the window
	hWnd = CreateWindowEx(WS_EX_TOPMOST, L"Splash", NULL, WS_POPUP, 0, 0, bm.bmWidth + (padding * 2), bm.bmHeight + (padding * 2), NULL, NULL, hInstance, NULL);

	// Center the window
	RECT rc;
	GetWindowRect(hWnd, &rc);
	SetWindowPos(hWnd, NULL, (GetSystemMetrics(SM_CXSCREEN) - rc.right) / 2, (GetSystemMetrics(SM_CYSCREEN) - rc.bottom) / 2, 0, 0, SWP_NOZORDER | SWP_NOSIZE);
}

void Splash::Show()
{
	// Display the window
	ShowWindow(hWnd, SW_SHOW);
	UpdateWindow(hWnd);
}

void Splash::Hide()
{
	// Hide the window
	ShowWindow(hWnd, SW_HIDE);
}

Splash::~Splash()
{
	DestroyWindow(hWnd);
	DeleteObject(hBitmap);
	UnregisterClass(L"Splash", NULL);
	g_pSplash = NULL;
}
