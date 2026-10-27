import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var store: AppStore

    var body: some View {
        Group {
            if store.connected {
                TabView {
                    RecordsView(qb: false).tabItem { Label("入库", systemImage: "archivebox") }
                    RecordsView(qb: true).tabItem { Label("qB", systemImage: "arrow.down.circle") }
                    RSSView().tabItem { Label("RSS", systemImage: "dot.radiowaves.left.and.right") }
                    NavigationStack { FilesView(path: "/") }.tabItem { Label("文件", systemImage: "folder") }
                    MoreView().tabItem { Label("更多", systemImage: "ellipsis.circle") }
                }
            } else { ConnectionView() }
        }
        .task { await store.resume() }
        .safeAreaInset(edge: .bottom) { OperationNotice() }
    }
}

struct ConnectionView: View {
    @EnvironmentObject private var store: AppStore
    @State private var draft = ServerConfig()
    @State private var username = ""
    @State private var password = ""
    @State private var otp = ""
    @State private var useToken = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Label("RSS一条龙", systemImage: "square.stack.3d.up")
                        .font(.title2.bold()).padding(.vertical, 12)
                    TextField("实例名称", text: $draft.instanceName)
                    TextField("MoviePilot 地址", text: $draft.baseURL)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                        .accessibilityIdentifier("serverAddress")
                }
                Section {
                    Toggle("使用访问令牌", isOn: $useToken)
                    if useToken {
                        SecureField("Bearer 访问令牌", text: $draft.token).textContentType(.password)
                            .accessibilityIdentifier("bearerToken")
                    } else {
                        TextField("MP 用户名", text: $username).textContentType(.username)
                            .textInputAutocapitalization(.never).autocorrectionDisabled()
                        SecureField("MP 密码", text: $password).textContentType(.password)
                        TextField("动态验证码（如已启用）", text: $otp)
                            .keyboardType(.numberPad).textContentType(.oneTimeCode)
                    }
                }
                Section {
                    Button {
                        Task { await store.connect(draft, username: useToken ? "" : username, password: password, otp: otp) }
                    } label: {
                        HStack { Spacer(); if store.busy { ProgressView() }; Text("连接 MoviePilot"); Spacer() }
                    }
                    .disabled(store.busy || draft.baseURL.isEmpty || (useToken ? draft.token.isEmpty : username.isEmpty || password.isEmpty))
                }
            }
            .navigationTitle("连接服务器")
            .accessibilityIdentifier("connectionForm")
            .onAppear { draft = store.config; useToken = !draft.token.isEmpty }
        }
    }
}

struct MoreView: View {
    @EnvironmentObject private var store: AppStore
    @State private var disconnect = false

    var body: some View {
        NavigationStack {
            List {
                Section("服务器") {
                    LabeledContent(store.config.instanceName, value: store.overview["plugin"]["version"].text)
                    NavigationLink { OverviewView() } label: { Label("运行总览", systemImage: "chart.bar") }
                    NavigationLink { ImportStatusView() } label: { Label("入库进度", systemImage: "tray.and.arrow.down") }
                    NavigationLink { TaskListView() } label: { Label("后台任务", systemImage: "clock.arrow.circlepath") }
                }
                Section("管理") {
                    NavigationLink { HistoryView() } label: { Label("RSS 历史", systemImage: "list.bullet.rectangle") }
                    NavigationLink { SiteListView() } label: { Label("站点身份", systemImage: "network") }
                    NavigationLink { PluginSettingsView() } label: { Label("插件设置", systemImage: "slider.horizontal.3") }
                    NavigationLink { ServerDocumentView(title: "目录规划", path: "layout") } label: { Label("目录规划", systemImage: "externaldrive") }
                    NavigationLink { ServerDocumentView(title: "依赖状态", path: "health") } label: { Label("依赖状态", systemImage: "stethoscope") }
                    NavigationLink { ServerDocumentView(title: "扫库回调记录", path: "emby/scheduledtasks/callbacks") } label: { Label("扫库回调记录", systemImage: "arrow.triangle.2.circlepath") }
                    NavigationLink { MaintenanceView() } label: { Label("数据维护", systemImage: "wrench.and.screwdriver") }
                }
                Section {
                    LabeledContent("客户端版本", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0.2.0")
                    Button("退出当前服务器", role: .destructive) { disconnect = true }
                }
            }
            .navigationTitle("更多")
            .confirmationDialog("退出当前服务器？", isPresented: $disconnect, titleVisibility: .visible) {
                Button("退出登录", role: .destructive) { store.disconnect() }
            }
        }
    }
}

struct OverviewView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        List {
            Section("记录统计") {
                ForEach(store.overview["counts"].object.keys.sorted(), id: \.self) { key in
                    LabeledContent(fieldTitle(key), value: store.overview["counts"][key].text)
                }
            }
            Section("运行任务") {
                ForEach(activeTasks) { task in
                    NavigationLink { TaskDetailView(id: task.id) } label: { TaskRow(item: task) }
                }
                if activeTasks.isEmpty { Text("当前没有运行中的任务").foregroundStyle(.secondary) }
            }
            Section { JSONDetails(value: store.overview["pending_import"]) }
        }
        .navigationTitle("运行总览")
        .refreshable { await store.refreshOverview() }
        .task { await store.refreshOverview() }
    }
    private var activeTasks: [Record] {
        let values = [store.overview["qb_task"], store.overview["manual_task"]] + store.overview["rss_tasks"].array
        return values.filter { !$0["id"].text.isEmpty }.map { Record(value: $0) }
    }
}
