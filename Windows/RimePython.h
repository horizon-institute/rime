#pragma once

void *StartRimeServer(void(*OnServerStarted)(void *), void *data);
void StopRimeServer(void *handle);
