# Melted Talker

A translator that stays on this computer and can be opened on a phone on the same Wi-Fi. It detects a language, or uses the one you pick, and turns the words into the language you chose. The words go to Google Translate. Nothing is saved.

The page that explains the Android app and offers the APK is [meltedlamp.github.io/translator](https://meltedlamp.github.io/translator/).

Download [To-English.apk](https://github.com/meltedlamp/translator/releases/download/v1.0.0/To-English.apk) (version 1.0). Open the file on an Android phone and allow the install.

## On this computer

Run `start.bat`. Python has to be installed. The translator stays in the tray.

- Select text in Discord or any other app and press `Ctrl+Alt+E`. A card stays on top of that app with the translation. Paste puts it back where you were typing.
- Copy text and the same card can appear on top.
- Hold the right `Ctrl` key, speak, and release. The words are cleaned up and typed into the box that already has the cursor. Press `Ctrl+Alt+Space` to keep talking without holding the key.
- The tray icon can pause translation, turn voice typing off, or stop launching with Windows.
- The page remembers the From and Into languages and uses them for selected text.
- Open the page and it shows this computer’s address and a QR code, so a phone on the same Wi-Fi can open the same translator. The laptop stays on.

## On a phone

The Android app is Melted Talker. Paste or type, tap Translate, or share text into the app from somewhere else. It can stay on in the background, including after the phone restarts. A passage should stay under 12,000 characters.

You can also open the computer’s page in the phone’s browser and add it to the home screen. Both devices need the same Wi-Fi, and the computer has to stay running.

## Changes

Newest first. Each new change goes at the top of this list.

### 13 October 2026

- The translator page loads this computer’s phone address as soon as it opens, so the QR code and link are ready without an extra step.
- The chosen From and Into languages are remembered and used when selected text is translated.
- The translator stays running in the background on a dark page, and text can be turned into any language, not only English.
- Hold-to-talk voice typing puts speech into the focused text box. The Android app, its background service, and the share-in translator were added in the same change.

### 6 October 2026

- The public page is named Melted Talker and uses the cat photo as its background.
- A page explains the Android app and offers the APK.
- A local desk detects any language and turns it into English. That first version is the tray app, the page, and the local server.
