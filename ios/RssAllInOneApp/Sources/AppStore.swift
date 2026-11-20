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
    @Published private(set) var analysisTask: JSONValue = .null
    var client: APIClient { APIClient(config: config) }
    private var uiTesting: Bool {
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("--ui-testing")
        #else
        return false
        #endif
    }

    init() {
        if uiTesting { return }
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
            if !uiTesting {
                try Credentials.save(next.token)
                var saved = next
                saved.token = ""
                UserDefaults.standard.set(try JSONEncoder().encode(saved), forKey: "rssallinone.server")
            }
            config = next
            overview = snapshot
            analysisTask = snapshot["analysis_task"]
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
            analysisTask = snapshot["analysis_task"]
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
            generation += 1
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

    func analyze(_ item: Record, kind: String, qb: Bool) async {
        guard item.canAnalyze(kind, qb: qb),
              !["queued", "running"].contains(analysisTask["state"].text) else { return }
        let body: JSONValue = .object(["media_id": .string(item.analysisID(qb: qb)), "kind": .string(kind)])
        analysisTask = .object(["state": .string("queued"), "result": body])
        if let result = await perform("media/analysis/run", body: body) {
            analysisTask = .object(["id": result["task_id"], "state": .string("queued"), "result": body])
        } else {
            await refreshOverview()
        }
    }

    func monitorAnalysis() async {
        let id = analysisTask["id"].text
        let current = config
        guard connected, !id.isEmpty else { return }
        while !Task.isCancelled && connected && config == current && analysisTask["id"].text == id {
            do {
                let result = try await client.get("tasks/\(id)")
                try Task.checkCancellation()
                guard config == current, analysisTask["id"].text == id else { return }
                let task = result["task"]
                guard !task.object.isEmpty else { throw APIError.server("读取提取进度失败") }
                analysisTask = task
                if !["queued", "running"].contains(task["state"].text) {
                    generation += 1
                    if task["state"].text == "succeeded" { notice = "提取完成，卡片状态已更新" }
                    else { error = task["error_message"].text.nonempty ?? "提取失败，请查看后台任务" }
                    return
                }
            } catch {
                if Task.isCancelled || config != current { return }
                report(error)
            }
            do { try await Task.sleep(for: .seconds(2)) } catch { return }
        }
    }

    func disconnect() {
        if !uiTesting {
            try? Credentials.save("")
            UserDefaults.standard.removeObject(forKey: "rssallinone.server")
        }
        config = ServerConfig()
        overview = .object([:])
        analysisTask = .null
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
