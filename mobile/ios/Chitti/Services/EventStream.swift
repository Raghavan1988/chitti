import Foundation

/// Minimal SSE client for GET /v1/sessions/{id}/events.
final class EventStream {
    private var task: URLSessionDataTask?
    private var session: URLSession?
    private var buffer = Data()

    func connect(
        baseURL: String,
        apiKey: String,
        sessionId: String,
        onEvent: @escaping (StreamEvent) -> Void,
        onError: @escaping (String) -> Void
    ) {
        stop()
        guard var components = URLComponents(string: baseURL) else {
            onError("Bad base URL")
            return
        }
        // Normalize path join
        let basePath = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let suffix = "v1/sessions/\(sessionId)/events"
        components.path = "/" + ([basePath, suffix].filter { !$0.isEmpty }.joined(separator: "/"))

        guard let url = components.url else {
            onError("Bad events URL")
            return
        }

        var req = URLRequest(url: url)
        req.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        req.timeoutInterval = 60 * 60

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 60 * 60
        let urlSession = URLSession(configuration: config, delegate: StreamDelegate(
            onChunk: { [weak self] data in
                self?.consume(data: data, onEvent: onEvent)
            },
            onError: onError
        ), delegateQueue: nil)
        self.session = urlSession
        let task = urlSession.dataTask(with: req)
        self.task = task
        task.resume()
    }

    func stop() {
        task?.cancel()
        task = nil
        session?.invalidateAndCancel()
        session = nil
        buffer.removeAll()
    }

    private func consume(data: Data, onEvent: @escaping (StreamEvent) -> Void) {
        buffer.append(data)
        guard var text = String(data: buffer, encoding: .utf8) else { return }

        while let range = text.range(of: "\n\n") {
            let block = String(text[..<range.lowerBound])
            text = String(text[range.upperBound...])
            parseBlock(block, onEvent: onEvent)
        }
        buffer = Data(text.utf8)
    }

    private func parseBlock(_ block: String, onEvent: (StreamEvent) -> Void) {
        var eventName = "message"
        var dataLines: [String] = []
        for line in block.split(separator: "\n", omittingEmptySubsequences: false) {
            let s = String(line)
            if s.hasPrefix(":") { continue }
            if s.hasPrefix("event:") {
                eventName = s.dropFirst(6).trimmingCharacters(in: .whitespaces)
            } else if s.hasPrefix("data:") {
                dataLines.append(s.dropFirst(5).trimmingCharacters(in: .whitespaces))
            }
        }
        guard !dataLines.isEmpty else { return }
        let raw = dataLines.joined(separator: "\n")
        guard let rawData = raw.data(using: .utf8) else { return }
        // Server sends {"kind":..., "payload":...}
        if let obj = try? JSONDecoder().decode(StreamEvent.self, from: rawData) {
            onEvent(obj)
            return
        }
        // Fallback: wrap
        if let payload = try? JSONDecoder().decode(AnyCodable.self, from: rawData) {
            // Construct via JSON re-encode
            let wrapped = "{\"kind\":\"\(eventName)\",\"payload\":\(raw)}"
            if let d = wrapped.data(using: .utf8),
               let obj = try? JSONDecoder().decode(StreamEvent.self, from: d) {
                onEvent(obj)
            } else {
                _ = payload
            }
        }
    }
}

private final class StreamDelegate: NSObject, URLSessionDataDelegate {
    let onChunk: (Data) -> Void
    let onError: (String) -> Void

    init(onChunk: @escaping (Data) -> Void, onError: @escaping (String) -> Void) {
        self.onChunk = onChunk
        self.onError = onError
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        onChunk(data)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error = error, (error as NSError).code != NSURLErrorCancelled {
            onError(error.localizedDescription)
        }
    }
}
