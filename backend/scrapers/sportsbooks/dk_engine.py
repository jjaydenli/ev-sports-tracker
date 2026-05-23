"""DraftKings Playwright scraper with accordion-targeting roadmap."""

import asyncio

from loguru import logger
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from config.api_headers import DK_USER_AGENT
from scrapers.base_scraper import BaseScraper
from utils.formatting import parse_dk_points_prop

MARKET_SELECTOR = '[data-testid="market-mapping-template-8"]'
AD_BLOCK_DOMAINS = ["google-analytics", "doubleclick", "facebook", "segment"]


async def scrape_game_page(context, url: str) -> list[dict]:
    """Scrape normalized points props from a single DraftKings event page."""
    page = await context.new_page()

    await page.route("**/*.{png,jpg,jpeg,svg,webp,gif}", lambda route: route.abort())
    await page.route(
        lambda request_url: any(domain in request_url for domain in AD_BLOCK_DOMAINS),
        lambda route: route.abort(),
    )

    logger.info(f"Scraping: {url}")
    await page.goto(url, wait_until="commit")

    try:
        await page.wait_for_selector(MARKET_SELECTOR, timeout=5000)
        texts = await page.locator(MARKET_SELECTOR).all_inner_texts()
        raw_props = [text.replace("\n", " | ") for text in texts if text]
    except Exception as exc:
        logger.error(f"Failed to extract from {url}: {exc}")
        raw_props = []
    finally:
        await page.close()

    structured_props = []
    for raw_prop in raw_props:
        parsed = parse_dk_points_prop(raw_prop)
        if parsed:
            structured_props.append(parsed)

    return structured_props


class DraftKingsEngine(BaseScraper):
    sportsbook_name = "DraftKings"

    def __init__(self, game_urls: list[str] | None = None):
        self.game_urls = game_urls or []

    async def authenticate(self) -> str | None:
        return None

    async def scrape(self) -> list[dict]:
        if not self.game_urls:
            logger.warning("No DraftKings game URLs configured.")
            return []

        all_game_props = []
        async with Stealth().use_async(async_playwright()) as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=DK_USER_AGENT)

            for url in self.game_urls:
                game_props = await scrape_game_page(context, url)
                all_game_props.extend(game_props)

            await browser.close()

        return all_game_props


async def main(game_urls: list[str]):
    """Scrape configured DraftKings event URLs and persist normalized props."""
    engine = DraftKingsEngine(game_urls=game_urls)
    output_path = "data/processed/dk_master_board.json"
    props = await engine.run(output_path)
    logger.success(f"pipeline complete: saved {len(props)} props to {output_path}")


if __name__ == "__main__":
    sample_urls = [
        "https://sportsbook.draftkings.com/event/orl-magic-%2540-det-pistons/34065791?category=all-odds&subcategory=points",
        "https://sportsbook.draftkings.com/event/tor-raptors-%40-cle-cavaliers/34058465?category=all-odds&subcategory=points",
    ]
    asyncio.run(main(sample_urls))
