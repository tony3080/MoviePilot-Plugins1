import Foundation
import SwiftUI

@MainActor
final class AppStore: ObservableObject {
    @Published private(set) var config = ServerConfig()
    @Published private(set) var connected = false
    @Published private(set) var overview: JSONValue = .object([:])
    @Published var error: String?
    @Published var notice: String?
    @Published private(set) var busy = false
    @Published private(set) var generation = 0
    var client: APIClient { APIClient(config: config) }

    init() {
        if let saved = UserDefaults.standard.data(forKey: "rssallinone.server"),
           var value = try? JSONDecoder().decode(ServerConfig.self, from: saved) {
            let migrated = value.token
            value.token = Credentials.load().nonempty ?? migrated
            config = value
            if !migrated.isEmpty {
                try? Credentials.save(migrated)
                value.token = ""
                UserDefaults.standard.set(try? JSONEncoder().encode(value), forKey: "rssallinone.server")
            }
        }
    }

    func connect(_ candidate: ServerConfig, username: String, password: String, otp: String) async {
        guard !busy else { return }
        busy = true
        error = nil
        defer { busy = false }
        do {
            var next = candidate
            next.baseURL = next.baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
            if !username.isEmpty {
                next.token = try await APIClient(config: next).login(username: username, password: password, otp: otp)
            }
            guard !next.token.isEmpty else { throw APIError.server("请登录 MP，或填写有效的 Bearer 访问令牌") }
            let snapshot = try await APIClient(config: next).get("overview")
            try Credentials.save(next.token)
            var saved = next
            saved.token = ""
            UserDefaults.standard.set(try JSONEncoder().encode(saved), forKey: "rssallinone.server")
            config = next
            overview = snapshot
            generation += 1
            connected = true
        } catch { self.error = error.localizedDescription }
    }

    func resume() async {
        guard !config.baseURL.isEmpty, !config.token.isEmpty else { return }
        await connect(config, username: "", password: "", otp: "")
    }

    func refreshOverview() async {
        let current = config
        do {
            let snapshot = try await client.get("overview")
            guard current == config else { return }
            overview = snapshot
        } catch { report(error) }
    }

    @discardableResult
    func perform(_ path: String, body: JSONValue = .object([:]), method: String = "POST", plugin: Bool = true) async -> JSONValue? {
        guard !busy else { return nil }
        busy = true
        defer { busy = false }
        do {
            let result = try await client.send(path, body: body, method: method, plugin: plugin)
            notice = result["message"].text.nonempty ?? "操作已完成"
            generation += 1
            await refreshOverview()
            return result
        } catch {
            report(error)
            return nil
        }
    }

    func report(_ failure: Error) {
        if failure is CancellationError { return }
        if let urlError = failure as? URLError, urlError.code == .cancelled { return }
        error = failure.localizedDescription
        if case APIError.unauthorized = failure { connected = false }
    }

    func disconnect() {
        try? Credentials.save("")
        UserDefaults.standard.removeObject(forKey: "rssallinone.server")
        config = ServerConfig()
        overview = .object([:])
        connected = false
        generation += 1
    }
}

@MainActor
final class PageStore: ObservableObject {
    @Published private(set) var rows: [Record] = []
    @Published private(set) var total = 0
    @Published private(set) var loading = false
    @Published private(set) var extra: JSONValue = .null
    private var revision = UUID()
    private var queryKey = ""
    private let limit = 50

    func load(_ client: APIClient, path: String, query: [URLQueryItem] = [], more: Bool = false) async throws {
        let key = path + query.map { "\($0.name)=\($0.value ?? "")" }.joined(separator: "&")
        if more && (loading || queryKey != key || rows.count >= total) { return }
        let request = UUID()
        revision = request
        queryKey = key
        if !more { rows = []; total = 0; extra = .null }
        loading = true
        defer { if revision == request { loading = false } }
        let offset = more ? rows.count : 0
        let response = try await client.get(path, query: query + [
            URLQueryItem(name: "offset", value: String(offset)), URLQueryItem(name: "limit", value: String(limit))
        ])
        try Task.checkCancellation()
        guard request == revision else { return }
        let incoming = response["items"].array.map { Record(value: $0) }
        rows = more ? rows + incoming : incoming
        total = response["total"].int
        extra = response
    }
}
