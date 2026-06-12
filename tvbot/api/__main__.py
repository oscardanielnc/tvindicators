import uvicorn

import config

uvicorn.run("tvbot.api.app:app", host=config.API_HOST, port=config.API_PORT)
