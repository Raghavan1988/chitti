# Chitti iOS client

SwiftUI thin client for the Chitti mobile harness server.

## Open in Xcode

1. Create a new **iOS App** project named `Chitti` (SwiftUI, Swift).
2. Replace / add the sources under `Chitti/` from this folder.
3. Set iOS deployment target **17.0+**.
4. Add permissions to `Info.plist`:

```xml
<key>NSSpeechRecognitionUsageDescription</key>
<string>Chitti transcribes your voice to run personal ops tasks.</string>
<key>NSMicrophoneUsageDescription</key>
<string>Chitti uses the mic for push-to-talk.</string>
<!-- Simulator / local server only; remove for App Store ATS -->
<key>NSAppTransportSecurity</key>
<dict>
  <key>NSAllowsLocalNetworking</key>
  <true/>
</dict>
```

5. Run the server on your Mac:

```bash
export ODYSSEUS_API_KEY=...
export CHITTI_API_KEY=dev-key-change-me
python3 -m server
```

6. In the app **Settings**, set:
   - Base URL: `http://127.0.0.1:8787` (Simulator) or `http://<your-lan-ip>:8787` (device)
   - API key: same as `CHITTI_API_KEY`

## Layout

```
Chitti/
  ChittiApp.swift          # @main
  Models.swift             # message / event types
  Services/
    APIClient.swift        # REST
    EventStream.swift      # SSE
    SpeechService.swift    # push-to-talk STT
  Features/
    ChatView.swift
    SettingsView.swift
    ApprovalCard.swift
```

This tree is source-only (no `.xcodeproj` checked in) so it stays editable on Linux CI; generate the Xcode project on a Mac.
