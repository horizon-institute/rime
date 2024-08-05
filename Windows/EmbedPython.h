#pragma once
#include <string>

void InitEmbedPython(const std::wstring pythonInstallDir, void(*onStart)(void*), wchar_t* logFilename, void* param);
void StopEmbedPythonThread();