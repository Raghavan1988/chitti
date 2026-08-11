import Foundation
import AVFoundation
import Speech

/// Push-to-talk speech recognition + simple TTS for final answers.
final class SpeechService: NSObject, ObservableObject {
    @Published var isRecording = false
    @Published var liveTranscript = ""
    /// True while server-synthesized briefing audio is playing.
    @Published var isPlaying = false

    private let audioEngine = AVAudioEngine()
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let recognizer = SFSpeechRecognizer()
    private let synthesizer = AVSpeechSynthesizer()
    private var player: AVAudioPlayer?

    func requestPermissions() async -> Bool {
        let speech = await withCheckedContinuation { (cont: CheckedContinuation<Bool, Never>) in
            SFSpeechRecognizer.requestAuthorization { status in
                cont.resume(returning: status == .authorized)
            }
        }
        let mic: Bool = await withCheckedContinuation { cont in
            AVAudioSession.sharedInstance().requestRecordPermission { ok in
                cont.resume(returning: ok)
            }
        }
        return speech && mic
    }

    func start() throws {
        stop()
        liveTranscript = ""
        let session = AVAudioSession.sharedInstance()
        try session.setCategory(.record, mode: .measurement, options: .duckOthers)
        try session.setActive(true, options: .notifyOthersOnDeactivation)

        recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
        guard let recognitionRequest else { return }
        recognitionRequest.shouldReportPartialResults = true

        let input = audioEngine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
            recognitionRequest.append(buffer)
        }
        audioEngine.prepare()
        try audioEngine.start()
        isRecording = true

        recognitionTask = recognizer?.recognitionTask(with: recognitionRequest) { [weak self] result, error in
            guard let self else { return }
            if let result {
                DispatchQueue.main.async {
                    self.liveTranscript = result.bestTranscription.formattedString
                }
            }
            if error != nil || (result?.isFinal ?? false) {
                DispatchQueue.main.async {
                    self.stop()
                }
            }
        }
    }

    func stop() {
        if audioEngine.isRunning {
            audioEngine.stop()
            audioEngine.inputNode.removeTap(onBus: 0)
        }
        recognitionRequest?.endAudio()
        recognitionRequest = nil
        recognitionTask?.cancel()
        recognitionTask = nil
        isRecording = false
    }

    func speak(_ text: String) {
        let utter = AVSpeechUtterance(string: text)
        utter.voice = AVSpeechSynthesisVoice(language: Locale.current.identifier)
        synthesizer.speak(utter)
    }

    /// Play server-synthesized digest audio (mp3). Returns false if the bytes
    /// couldn't be decoded, so the caller can fall back to on-device `speak`.
    @discardableResult
    func play(_ data: Data) -> Bool {
        do {
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .spokenAudio, options: .duckOthers)
            try session.setActive(true)
            let p = try AVAudioPlayer(data: data)
            p.delegate = self
            player = p
            p.play()
            isPlaying = true
            return true
        } catch {
            isPlaying = false
            return false
        }
    }

    func stopPlayback() {
        player?.stop()
        player = nil
        isPlaying = false
    }
}

extension SpeechService: AVAudioPlayerDelegate {
    func audioPlayerDidFinishPlaying(_ player: AVAudioPlayer, successfully flag: Bool) {
        DispatchQueue.main.async { self.isPlaying = false }
    }
}
