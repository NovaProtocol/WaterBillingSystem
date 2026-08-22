class TestDev:
    def test_index(self, page):
        page.goto("http://127.0.0.1:9104/developer/")
        assert page.locator("body").inner_text() != ""
