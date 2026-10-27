import XCTest

final class AppFlowTests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments = ["--ui-testing", "-AppleLanguages", "(zh-Hans)", "-AppleLocale", "zh_CN"]
        app.launch()
        let address = app.textFields["serverAddress"]
        XCTAssertTrue(address.waitForExistence(timeout: 10))
        address.tap()
        address.typeText("http://127.0.0.1:8767")
        app.buttons["dismissKeyboard"].tap()
        app.switches["使用访问令牌"].coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        let token = app.secureTextFields["bearerToken"]
        XCTAssertTrue(token.waitForExistence(timeout: 5))
        token.tap()
        token.typeText("fixture-token")
        app.buttons["dismissKeyboard"].tap()
        app.buttons["连接 MoviePilot"].tap()
        XCTAssertTrue(app.tabBars.buttons["入库"].waitForExistence(timeout: 15))
    }

    func testMediaDetailsAndManualIdentification() {
        let film = app.staticTexts["测试电影"]
        XCTAssertTrue(film.waitForExistence(timeout: 10))
        capture("01-media-list")
        film.tap()
        XCTAssertTrue(app.links["P · 种子页面"].exists || app.buttons["P · 种子页面"].exists)
        app.buttons["编辑识别与标签"].tap()
        XCTAssertTrue(app.navigationBars["编辑识别"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.switches["国配"].exists)
        XCTAssertTrue(app.switches["特效"].exists)
        app.switches["特效"].coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        capture("02-identification")
        app.buttons["确认"].tap()
        XCTAssertTrue(app.navigationBars["入库管理"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["识别已更新"].waitForExistence(timeout: 5))
    }

    func testMediaAndQBLabelsWrapAcrossRows() {
        XCTAssertTrue(app.staticTexts["测试电影"].waitForExistence(timeout: 10))
        assertWrappedLabels()
        XCTAssertTrue(app.staticTexts["目录已存在（0/12）"].exists)
        let source = app.buttons["源文件名"].firstMatch
        XCTAssertTrue(source.exists)
        XCTAssertLessThan(source.frame.maxY - app.staticTexts["测试电影"].frame.minY, 190)
        capture("08-media-wrapped-labels")
        source.tap()
        XCTAssertTrue(app.staticTexts["Test.Movie.2026.1080p.mkv"].waitForExistence(timeout: 5))
        app.buttons["隐藏源文件名"].tap()
        XCTAssertFalse(app.staticTexts["Test.Movie.2026.1080p.mkv"].exists)

        app.tabBars.buttons["qB"].tap()
        XCTAssertTrue(app.staticTexts["测试下载任务"].waitForExistence(timeout: 10))
        assertWrappedLabels()
        XCTAssertTrue(app.buttons["删任务"].exists)
        capture("09-qb-wrapped-labels")
    }

    private func assertWrappedLabels() {
        let status = app.staticTexts["已识别"].firstMatch
        let resolution = app.staticTexts["1080p"].firstMatch
        let customization = app.staticTexts["REMUX@U版"].firstMatch
        let mandarin = app.staticTexts["国配"].firstMatch
        XCTAssertTrue(status.exists)
        XCTAssertTrue(resolution.exists)
        XCTAssertTrue(customization.exists)
        XCTAssertTrue(mandarin.exists)
        XCTAssertEqual(status.frame.minY, resolution.frame.minY, accuracy: 2)
        XCTAssertGreaterThan(resolution.frame.minX, status.frame.minX)
        XCTAssertGreaterThan(mandarin.frame.minY, status.frame.minY)
        XCTAssertLessThan(customization.frame.maxX, app.frame.maxX)
    }

    func testQBAndPresenceCheck() {
        app.tabBars.buttons["qB"].tap()
        XCTAssertTrue(app.staticTexts["测试下载任务"].waitForExistence(timeout: 10))
        capture("03-qb-list")
        app.buttons["qbActions"].coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        capture("03b-qb-menu")
        app.buttons["核对待下载任务"].tap()
        XCTAssertTrue(app.buttons["取消"].waitForExistence(timeout: 5))
        app.buttons["核对待下载任务"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["核对完成：保留 1 项"].waitForExistence(timeout: 10))
    }

    func testRSSConfigurationAndPreview() {
        app.tabBars.buttons["RSS"].tap()
        XCTAssertTrue(app.buttons["rss-task-task-1"].waitForExistence(timeout: 10))
        app.buttons["rss-task-task-1"].tap()
        XCTAssertTrue(app.navigationBars["任务配置"].waitForExistence(timeout: 5))
        capture("04-rss-editor")
        app.buttons["取消"].tap()
        XCTAssertTrue(app.navigationBars["RSS 任务"].waitForExistence(timeout: 5))
        app.buttons["rss-actions-task-1"].coordinate(withNormalizedOffset: CGVector(dx: 0.15, dy: 0.5)).tap()
        capture("04b-rss-menu")
        XCTAssertTrue(app.buttons["测试配置"].waitForExistence(timeout: 5))
        app.buttons["测试配置"].tap()
        XCTAssertTrue(app.navigationBars["RSS 测试结果"].waitForExistence(timeout: 10))
        capture("05-rss-preview")
        app.buttons["完成"].tap()
    }

    func testFilesAndSettings() {
        app.tabBars.buttons["文件"].tap()
        XCTAssertTrue(app.staticTexts["媒体目录"].waitForExistence(timeout: 10))
        app.staticTexts["媒体目录"].tap()
        XCTAssertTrue(app.staticTexts["测试文件.mkv"].waitForExistence(timeout: 10))
        capture("06-file-browser")
        app.tabBars.buttons["更多"].tap()
        app.buttons["插件设置"].tap()
        XCTAssertTrue(app.navigationBars["插件设置"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.switches["启用"].waitForExistence(timeout: 10))
        capture("07-settings")
    }

    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
