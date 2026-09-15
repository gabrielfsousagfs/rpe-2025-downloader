import asyncio
import os
import zipfile
from playwright.async_api import async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


def parse_ids(raw: str):
    """Aceita IDs separados por vírgula, ponto-e-vírgula ou quebra de linha."""
    ids = []
    for token in raw.replace("\n", ",").replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            ids.append(int(token))
        except ValueError:
            print(f"⚠️  Ignorando valor inválido na lista de IDs: '{token}'", flush=True)
    return ids


IDS_RAW = os.getenv("IDS", "")
IDS_LIST = parse_ids(IDS_RAW)

SAVE_FOLDER = "pdfs_rpe_2024"
ZIP_NAME = f"RPE_2025_{len(IDS_LIST)}_ids.zip"

# Tunables for performance / CI stability
DOWNLOAD_TIMEOUT_MS = int(os.getenv("DOWNLOAD_TIMEOUT_MS", "8000"))
GOTO_TIMEOUT_MS = int(os.getenv("GOTO_TIMEOUT_MS", "12000"))
REQUEST_DELAY_MS = int(os.getenv("REQUEST_DELAY_MS", "100"))

BASE_URL = "https://sistema-registropublicodeemissoesapi.fgv.br/GenerateReport/GenerateInventoryReport/{}/19/true"

os.makedirs(SAVE_FOLDER, exist_ok=True)


async def main():
    print("Script iniciado.", flush=True)

    if not IDS_LIST:
        print("❌ Nenhum ID válido foi fornecido (variável IDS vazia ou mal formatada).", flush=True)
        raise SystemExit(1)

    preview = ", ".join(str(i) for i in IDS_LIST[:10])
    sufixo = "..." if len(IDS_LIST) > 10 else ""
    print(f"Lista configurada: {len(IDS_LIST)} ID(s) -> {preview}{sufixo}", flush=True)
    print(
        f"Config: DOWNLOAD_TIMEOUT_MS={DOWNLOAD_TIMEOUT_MS}, GOTO_TIMEOUT_MS={GOTO_TIMEOUT_MS}, REQUEST_DELAY_MS={REQUEST_DELAY_MS}",
        flush=True,
    )
    download_count = 0

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(accept_downloads=True)
            page = await context.new_page()

            for participant_id in IDS_LIST:
                formatted_id = f"{participant_id:04d}"
                url = BASE_URL.format(formatted_id)

                try:
                    print(f"Tentando {formatted_id}", flush=True)

                    async with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as download_info:
                        try:
                            await page.goto(url, wait_until="commit", timeout=GOTO_TIMEOUT_MS)
                        except PlaywrightError as exc:
                            # Expected for endpoints that immediately return a file download.
                            if "Download is starting" not in str(exc):
                                raise

                    download = await download_info.value
                    path = os.path.join(SAVE_FOLDER, f"{formatted_id}.pdf")
                    await download.save_as(path)

                    download_count += 1
                    print(f"✔ PDF salvo {formatted_id}", flush=True)

                except PlaywrightTimeoutError:
                    print(f"✖ Timeout no download para {formatted_id}", flush=True)
                except Exception as exc:
                    print(f"✖ Falha em {formatted_id}: {exc}", flush=True)

                if REQUEST_DELAY_MS > 0:
                    await asyncio.sleep(REQUEST_DELAY_MS / 1000)

            await browser.close()
    except PlaywrightError as exc:
        print("Falha ao inicializar Playwright/Chromium.", flush=True)
        print(f"Detalhes: {exc}", flush=True)
        print(
            "Sugestão: garanta que o workflow execute `python -m playwright install --with-deps chromium` antes do script.",
            flush=True,
        )
        raise

    if download_count > 0:
        with zipfile.ZipFile(ZIP_NAME, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file in os.listdir(SAVE_FOLDER):
                zipf.write(os.path.join(SAVE_FOLDER, file), file)

        print(f"ZIP criado: {ZIP_NAME}", flush=True)

    print(f"Total de PDFs baixados: {download_count}", flush=True)


asyncio.run(main())
