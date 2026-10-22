# RX75 Stream Pad

A small Windows macro-pad and soundboard app for the ZIFRIEND RX75 Pro. It lets selected keyboard keys launch apps/files or websites, send shortcuts or another key, type saved text, show saved text or image popups, control media playback, and play sound clips.

## Setup

1. Keep the RX75 connected in wired mode while setting it up.
2. Install Python 3 for Windows if it is not already installed.
3. Double-click `install.bat` once.
4. Double-click `run.vbs` to open the app without a Command Prompt window. (`run.bat` is also available as a fallback launcher.)
5. Choose **Work**, **Streaming**, or **Gaming**, then add actions for that profile.
6. Turn on **Enable mapped keys** when you want the mappings active.

Mapped keys are intercepted, so their original key action does not happen while mappings are enabled. Unmapped keys continue to type normally. Press `Ctrl+Alt+F12` to toggle mappings on or off. Closing the app releases the hooks. The `run.vbs` launcher starts the app in the background and exits immediately, so there is no Command Prompt window to close. Avoid mapping keys you need for normal typing; F keys and keys you rarely use make good macro-pad buttons.

## Actions

- **Open app/file**: choose an executable, document, or other file.
- **Open website**: enter a full URL such as `https://example.com`.
- **Send shortcut**: enter a combination such as `Ctrl+Shift+M`.
- **Send another key**: enter a key such as `a`, `F5`, or `Enter`; the mapped key is intercepted and the selected key is sent in its place.
- **Type saved text**: enter a text snippet that is typed into the active app.
- **Show saved text popup**: enter multiline text to show in a simple, read-only notepad window.
- **Media control**: use `play/pause`, `next track`, `previous track`, `volume mute`, `volume up`, or `volume down`.
- **Play sound clip**: choose a WAV, MP3, or OGG file. Clips can overlap, up to the available playback channels.
- **Stop all sounds**: map a key to stop every currently playing clip.
- **Show image popup**: choose a PNG, JPG, GIF, BMP, or WebP image.

For image and saved-text popups, choose **Until closed** or an automatic close time of 1, 3, 5, 10, 30, or 60 seconds. Press Escape or use the window close button to dismiss a popup early.

Use the **Sound volume** slider to set the playback level. You can make one key per sound and a separate stop key, like a basic Stream Deck soundboard. Image popups open in a separate window and are resized to fit on screen. Saved-text popups support multiple lines.

The `mappings.json` file is created beside the app and stores the key assignments. Back it up to preserve your setup. Keep sound and image files at their saved paths; the app stores paths rather than copying media into the project.

Work, Streaming, and Gaming are included by default. Use **New profile** to add more profiles. Custom profiles can be deleted; the three starter profiles are protected.

## Lighting

Use ZIFRIEND's RX keyboard software for RGB lighting and per-key colors. This first version controls Windows actions; it does not change the keyboard firmware or directly control RGB effects.
