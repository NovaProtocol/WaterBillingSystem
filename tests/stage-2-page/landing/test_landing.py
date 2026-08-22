class TestLanding:
    def test_home(self, page):
        page.goto("http://127.0.0.1:9101/")
        assert page.title() != ""

    def test_offerings(self, page):
        page.goto("http://127.0.0.1:9101/offerings")
        assert "Model" in page.locator("body").inner_text()
