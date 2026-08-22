class TestStaff:
    def test_login(self, page):
        page.goto("http://127.0.0.1:9103/staff/login")
        assert page.locator("body").inner_text() != ""
