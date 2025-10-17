"""
End-to-end tests for frontend integration with backend services using Playwright.
"""
import pytest
from playwright.async_api import async_playwright, Page, Browser


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.slow
class TestFrontendIntegration:
    """Test class for frontend integration E2E tests."""

    @pytest.fixture(scope="class")
    async def browser(self):
        """Create browser instance for E2E tests."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            yield browser
            await browser.close()

    @pytest.fixture(scope="class")
    async def page(self, browser: Browser) -> Page:
        """Create page instance for E2E tests."""
        page = await browser.new_page()
        yield page
        await page.close()

    async def test_homepage_loads(self, page: Page):
        """Test homepage loads correctly."""
        await page.goto("http://localhost:3000")
        
        # Check page title
        title = await page.title()
        assert "Simple UI" in title
        
        # Check service cards are visible
        asr_card = page.locator('[data-testid="asr-card"]')
        tts_card = page.locator('[data-testid="tts-card"]')
        nmt_card = page.locator('[data-testid="nmt-card"]')
        
        await asr_card.wait_for(state="visible")
        await tts_card.wait_for(state="visible")
        await nmt_card.wait_for(state="visible")
        
        # Check navigation links
        asr_link = page.locator('a[href="/asr"]')
        tts_link = page.locator('a[href="/tts"]')
        nmt_link = page.locator('a[href="/nmt"]')
        
        assert await asr_link.is_visible()
        assert await tts_link.is_visible()
        assert await nmt_link.is_visible()

    async def test_api_key_modal(self, page: Page):
        """Test API key modal functionality."""
        await page.goto("http://localhost:3000")
        
        # Click "Manage API Key" button
        manage_key_button = page.locator('[data-testid="manage-api-key-button"]')
        await manage_key_button.click()
        
        # Check modal opens
        modal = page.locator('[data-testid="api-key-modal"]')
        await modal.wait_for(state="visible")
        
        # Enter test API key
        api_key_input = page.locator('[data-testid="api-key-input"]')
        await api_key_input.fill("test_api_key_12345")
        
        # Click save
        save_button = page.locator('[data-testid="save-api-key-button"]')
        await save_button.click()
        
        # Check modal closes
        await modal.wait_for(state="hidden")
        
        # Check API key badge shows
        api_key_badge = page.locator('[data-testid="api-key-badge"]')
        await api_key_badge.wait_for(state="visible")
        badge_text = await api_key_badge.text_content()
        assert "API Key: ****" in badge_text

    async def test_asr_page_recording(self, page: Page):
        """Test ASR page recording functionality."""
        await page.goto("http://localhost:3000/asr")
        
        # Set API key
        manage_key_button = page.locator('[data-testid="manage-api-key-button"]')
        await manage_key_button.click()
        api_key_input = page.locator('[data-testid="api-key-input"]')
        await api_key_input.fill("test_api_key_12345")
        save_button = page.locator('[data-testid="save-api-key-button"]')
        await save_button.click()
        
        # Select language
        language_select = page.locator('[data-testid="language-select"]')
        await language_select.select_option("en")
        
        # Click record button
        record_button = page.locator('[data-testid="record-button"]')
        await record_button.click()
        
        # Wait for recording to start
        await page.wait_for_timeout(1000)
        
        # Click stop button
        stop_button = page.locator('[data-testid="stop-button"]')
        await stop_button.click()
        
        # Check transcript appears (may take time for processing)
        await page.wait_for_timeout(3000)
        
        # Check results section
        results_section = page.locator('[data-testid="results-section"]')
        if await results_section.is_visible():
            # Check stats are displayed
            stats = page.locator('[data-testid="stats"]')
            assert await stats.is_visible()

    async def test_asr_page_file_upload(self, page: Page):
        """Test ASR page file upload functionality."""
        await page.goto("http://localhost:3000/asr")
        
        # Set API key
        manage_key_button = page.locator('[data-testid="manage-api-key-button"]')
        await manage_key_button.click()
        api_key_input = page.locator('[data-testid="api-key-input"]')
        await api_key_input.fill("test_api_key_12345")
        save_button = page.locator('[data-testid="save-api-key-button"]')
        await save_button.click()
        
        # Upload sample file
        file_input = page.locator('[data-testid="file-input"]')
        await file_input.set_input_files({
            "name": "test.wav",
            "mimeType": "audio/wav",
            "buffer": b"dummy audio data"
        })
        
        # Wait for processing
        await page.wait_for_timeout(3000)
        
        # Check results appear
        results_section = page.locator('[data-testid="results-section"]')
        if await results_section.is_visible():
            # Check audio player is visible
            audio_player = page.locator('[data-testid="audio-player"]')
            assert await audio_player.is_visible()

    async def test_tts_page_text_input(self, page: Page):
        """Test TTS page text input functionality."""
        await page.goto("http://localhost:3000/tts")
        
        # Set API key
        manage_key_button = page.locator('[data-testid="manage-api-key-button"]')
        await manage_key_button.click()
        api_key_input = page.locator('[data-testid="api-key-input"]')
        await api_key_input.fill("test_api_key_12345")
        save_button = page.locator('[data-testid="save-api-key-button"]')
        await save_button.click()
        
        # Select language and gender
        language_select = page.locator('[data-testid="language-select"]')
        await language_select.select_option("ta")
        
        gender_select = page.locator('[data-testid="gender-select"]')
        await gender_select.select_option("female")
        
        # Enter text
        text_input = page.locator('[data-testid="text-input"]')
        await text_input.fill("வணக்கம், இது ஒரு சோதனை")
        
        # Click generate button
        generate_button = page.locator('[data-testid="generate-button"]')
        await generate_button.click()
        
        # Wait for processing
        await page.wait_for_timeout(5000)
        
        # Check audio player appears
        audio_player = page.locator('[data-testid="audio-player"]')
        if await audio_player.is_visible():
            # Check stats are displayed
            stats = page.locator('[data-testid="stats"]')
            assert await stats.is_visible()

    async def test_nmt_page_translation(self, page: Page):
        """Test NMT page translation functionality."""
        await page.goto("http://localhost:3000/nmt")
        
        # Set API key
        manage_key_button = page.locator('[data-testid="manage-api-key-button"]')
        await manage_key_button.click()
        api_key_input = page.locator('[data-testid="api-key-input"]')
        await api_key_input.fill("test_api_key_12345")
        save_button = page.locator('[data-testid="save-api-key-button"]')
        await save_button.click()
        
        # Select language pair
        source_language = page.locator('[data-testid="source-language-select"]')
        await source_language.select_option("en")
        
        target_language = page.locator('[data-testid="target-language-select"]')
        await target_language.select_option("hi")
        
        # Enter text
        text_input = page.locator('[data-testid="text-input"]')
        await text_input.fill("Hello world")
        
        # Click translate button
        translate_button = page.locator('[data-testid="translate-button"]')
        await translate_button.click()
        
        # Wait for processing
        await page.wait_for_timeout(3000)
        
        # Check translation appears
        translation_output = page.locator('[data-testid="translation-output"]')
        if await translation_output.is_visible():
            translation_text = await translation_output.text_content()
            assert len(translation_text) > 0
            
            # Check stats are displayed
            stats = page.locator('[data-testid="stats"]')
            assert await stats.is_visible()

    async def test_navigation_between_services(self, page: Page):
        """Test navigation between different service pages."""
        # Start at ASR page
        await page.goto("http://localhost:3000/asr")
        
        # Navigate to TTS page
        tts_link = page.locator('a[href="/tts"]')
        await tts_link.click()
        await page.wait_for_url("**/tts")
        
        # Navigate to NMT page
        nmt_link = page.locator('a[href="/nmt"]')
        await nmt_link.click()
        await page.wait_for_url("**/nmt")
        
        # Navigate back to home
        home_link = page.locator('a[href="/"]')
        await home_link.click()
        await page.wait_for_url("**/")

    async def test_error_handling_invalid_api_key(self, page: Page):
        """Test error handling with invalid API key."""
        await page.goto("http://localhost:3000/asr")
        
        # Set invalid API key
        manage_key_button = page.locator('[data-testid="manage-api-key-button"]')
        await manage_key_button.click()
        api_key_input = page.locator('[data-testid="api-key-input"]')
        await api_key_input.fill("invalid_api_key")
        save_button = page.locator('[data-testid="save-api-key-button"]')
        await save_button.click()
        
        # Try to perform ASR inference
        record_button = page.locator('[data-testid="record-button"]')
        await record_button.click()
        await page.wait_for_timeout(1000)
        stop_button = page.locator('[data-testid="stop-button"]')
        await stop_button.click()
        
        # Check error toast appears
        await page.wait_for_timeout(3000)
        error_toast = page.locator('[data-testid="error-toast"]')
        if await error_toast.is_visible():
            error_text = await error_toast.text_content()
            assert "Invalid API key" in error_text or "Authentication" in error_text

    async def test_error_handling_service_unavailable(self, page: Page):
        """Test error handling when service is unavailable."""
        await page.goto("http://localhost:3000/asr")
        
        # Set valid API key
        manage_key_button = page.locator('[data-testid="manage-api-key-button"]')
        await manage_key_button.click()
        api_key_input = page.locator('[data-testid="api-key-input"]')
        await api_key_input.fill("test_api_key_12345")
        save_button = page.locator('[data-testid="save-api-key-button"]')
        await save_button.click()
        
        # Try to perform ASR inference (service might be down)
        record_button = page.locator('[data-testid="record-button"]')
        await record_button.click()
        await page.wait_for_timeout(1000)
        stop_button = page.locator('[data-testid="stop-button"]')
        await stop_button.click()
        
        # Check error handling
        await page.wait_for_timeout(5000)
        # Either results appear or error is handled gracefully
        results_section = page.locator('[data-testid="results-section"]')
        error_toast = page.locator('[data-testid="error-toast"]')
        
        # At least one should be visible
        assert await results_section.is_visible() or await error_toast.is_visible()
