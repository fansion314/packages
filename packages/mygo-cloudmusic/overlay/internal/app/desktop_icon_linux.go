//go:build linux

package app

import (
	"log"

	"github.com/ebitengine/purego"
)

// configureDesktopIcon runs on the GTK main thread before any windows exist.
// Keep X11's WM_CLASS and Wayland's app_id aligned with the installed desktop
// entry, and give all windows (including Settings) the themed application icon.
func configureDesktopIcon() {
	for _, api := range []struct {
		library, symbol, value string
	}{
		{"libglib-2.0.so.0", "g_set_prgname", "dev.egoist.cloudmusic"},
		{"libgdk-3.so.0", "gdk_set_program_class", "dev.egoist.cloudmusic"},
		{"libgtk-3.so.0", "gtk_window_set_default_icon_name", "mygo-cloudmusic"},
	} {
		lib, err := purego.Dlopen(api.library, purego.RTLD_NOW|purego.RTLD_GLOBAL)
		if err != nil {
			log.Printf("configure desktop icon: %v", err)
			return
		}
		var set func(string)
		purego.RegisterLibFunc(&set, lib, api.symbol)
		set(api.value)
		purego.Dlclose(lib)
	}
}
