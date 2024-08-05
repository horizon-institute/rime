#pragma once


void InitEmbedPython(const wchar_t* pythonInstallDir, void(*onStart)(void*), wchar_t* logFilename, void* param);
void StopEmbedPythonThread();