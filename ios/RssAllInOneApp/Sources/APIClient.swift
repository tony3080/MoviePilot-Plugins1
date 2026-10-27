import Foundation

enum APIError: LocalizedError {
    case invalidURL, unauthorized, server(String)
    var errorDescription: String? {
        switch self {
        case .invalidURL: return "请输入有效的 MoviePilot HTTP 或 HTTPS 地址"
        case .unauthorized: return "登录已失效，请重新登录 MoviePilot"
        case .server(let message): return message
        }
    }
}

struct APIClient: Sendable {
    let config: ServerConfig
    var session: URLSession = .shared

    func url(_ path: String, query: [URLQueryItem] = []) throws -> URL {
        guard var parts = URLComponents(string: config.baseURL.trimmingCharacters(in: .whitespacesAndNewlines)),
              ["http", "https"].contains(parts.scheme?.lowercased() ?? ""), parts.host != nil,
              parts.user == nil, parts.password == nil else { throw APIError.invalidURL }
        var prefix = parts.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if prefix.hasSuffix("api/v1") { prefix = String(prefix.dropLast(6)).trimmingCharacters(in: CharacterSet(charactersIn: "/")) }
        parts.path = "/" + [prefix, "api/v1", path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))]
            .filter { !$0.isEmpty }.joined(separator: "/")
        parts.queryItems = query.isEmpty ? nil : query
        parts.fragment = nil
        guard let url = parts.url else { throw APIError.invalidURL }
        return url
    }

    func get(_ path: String, query: [URLQueryItem] = [], plugin: Bool = true) async throws -> JSONValue {
        try await request(path, method: "GET", query: query, plugin: plugin)
    }

    func send(_ path: String, body: JSONValue = .object([:]), method: String = "POST", plugin: Bool = true) async throws -> JSONValue {
        try await request(path, method: method, body: JSONEncoder().encode(body), plugin: plugin)
    }

    func login(username: String, password: String, otp: String) async throws -> String {
        var form = URLComponents()
        form.queryItems = [URLQueryItem(name: "username", value: username), URLQueryItem(name: "password", value: password)]
        if !otp.isEmpty { form.queryItems?.append(URLQueryItem(name: "otp_password", value: otp)) }
        let encoded = form.percentEncodedQuery?.replacingOccurrences(of: "+", with: "%2B").data(using: .utf8)
        let reply = try await request("login/access-token", method: "POST", body: encoded,
                                      plugin: false, contentType: "application/x-www-form-urlencoded", authenticate: false)
        guard !reply["access_token"].text.isEmpty else { throw APIError.server("登录成功但未返回访问令牌") }
        return reply["access_token"].text
    }

    private func request(
        _ path: String, method: String, query: [URLQueryItem] = [], body: Data? = nil,
        plugin: Bool, contentType: String = "application/json", authenticate: Bool = true
    ) async throws -> JSONValue {
        let path = plugin ? "plugin/RssAllInOne/" + path.trimmingCharacters(in: CharacterSet(charactersIn: "/")) : path
        var request = URLRequest(url: try url(path, query: query), timeoutInterval: 180)
        request.httpMethod = method
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if body != nil { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
        if authenticate, !config.token.isEmpty { request.setValue("Bearer \(config.token)", forHTTPHeaderField: "Authorization") }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw APIError.server("服务器没有返回 HTTP 响应") }
        let reply = try? JSONDecoder().decode(JSONValue.self, from: data)
        if http.statusCode == 401 {
            if reply?["mfa_methods"].array.isEmpty == false { throw APIError.server("需要二次验证，请填写动态验证码后重试") }
            if !authenticate { throw APIError.server(reply?["detail"].text ?? "登录失败") }
            throw APIError.unauthorized
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.server(reply?["detail"].text.nonempty ?? reply?["message"].text.nonempty ?? "HTTP \(http.statusCode)")
        }
        guard let reply else { throw APIError.server("服务器返回的数据无法解析，请检查 MP 地址及反向代理") }
        if case .bool(false) = reply["success"] {
            let failures = reply["results"].array.filter { !$0["success"].flag }.prefix(3).map { $0["message"].text }
            throw APIError.server(([reply["message"].text.nonempty ?? "操作失败"] + failures).joined(separator: "\n"))
        }
        return reply
    }
}
