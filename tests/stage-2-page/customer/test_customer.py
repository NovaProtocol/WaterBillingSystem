class TestCustomer:
    def test_identify(self, page):
        page.goto('http://127.0.0.1:9102/customer/')
        assert page.locator('body').inner_text() != ''
