/* CloutFox.exe: starts the bundled pythonw.exe with the app and returns. */
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR args, int show)
{
    wchar_t dir[32768];
    wchar_t command[32768];
    STARTUPINFOW startup = {sizeof(startup)};
    PROCESS_INFORMATION process;
    wchar_t *slash;
    DWORD length;

    (void)instance;
    (void)previous;
    (void)show;
    length = GetModuleFileNameW(NULL, dir, ARRAYSIZE(dir));
    if (length == 0 || length >= ARRAYSIZE(dir)) {
        return 1;
    }
    slash = wcsrchr(dir, L'\\');
    if (slash != NULL) {
        *slash = L'\0';
    }
    if (_snwprintf_s(command, ARRAYSIZE(command), _TRUNCATE,
                     L"\"%s\\python\\pythonw.exe\" \"%s\\app\\cloutfox_app.py\" %s",
                     dir, dir, args) < 0) {
        return 1;
    }
    if (!CreateProcessW(NULL, command, NULL, NULL, FALSE, 0, NULL, dir, &startup, &process)) {
        MessageBoxW(NULL, L"CloutFox could not start its Python runtime. Reinstall CloutFox.",
                    L"CloutFox", MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(process.hThread);
    CloseHandle(process.hProcess);
    return 0;
}
