#pragma once

#include "Resource.h"

class Splash
{
public:
	Splash(HINSTANCE hInstance, int nCmdShow);
	void Show();
	void Hide();
	virtual ~Splash();

	// friend splashproc
	friend LRESULT CALLBACK SplashWndProc(HWND hWnd, UINT message, WPARAM wParam, LPARAM lParam);

private:
	HWND hWnd;
	HANDLE hBitmap;
};