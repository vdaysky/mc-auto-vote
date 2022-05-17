import asyncio
import datetime
import json
import logging
import os
import re
import time

import aiohttp
from bs4 import BeautifulSoup

from logging import Logger
from dotenv import load_dotenv

load_dotenv()
ANTI_CAPTCHA_KEY = os.environ['ANTI_CAPTCHA_KEY']

logger = Logger(name="mc-auto-vote")
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9,uk;q=0.8",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "sec-ch-ua": "\" Not A;Brand\";v=\"99\", \"Chromium\";v=\"101\", \"Google Chrome\";v=\"101\"",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": "\"Windows\"",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "x-requested-with": "XMLHttpRequest",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.67 Safari/537.36"
}


class CaptchaSolver:

    def __init__(self):
        self.started_at = None
        self.finished_at = None

    def get_solution_time(self, format=None):
        if None in (self.started_at, self.finished_at):
            return None

        delta = self.finished_at - self.started_at

        if format is None:
            return delta

        return datetime.datetime.utcfromtimestamp(delta).strftime(format)

    async def solve(self):
        logger.info("start captcha solving...")
        self.started_at = datetime.datetime.now()

        async with aiohttp.ClientSession() as session:
            async with session.post("https://api.anti-captcha.com/createTask", json={
                "clientKey": ANTI_CAPTCHA_KEY,
                "task": {
                    "type": "RecaptchaV2TaskProxyless",
                    "websiteURL": "https://minecraft-server-list.com/server/218820/vote/",
                    "websiteKey": "6LczktcUAAAAAMCHTeFyeDeVFmMSIULBINyBWxmE",
                    "isInvisible": True,
                    "proxyType": "socks5",
                    "proxyAddress": os.environ['PROXY_SERVER'],
                    'proxyPort': os.environ['PROXY_PORT'],
                    "proxyLogin": os.environ['PROXY_USER'],
                    "proxyPassword": os.environ['PROXY_PWD'],
                    "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.67 Safari/537.36",
                }
            }) as response:
                json_resp = await response.json()
                if json_resp['errorId']:
                    logger.error(f"error: {response}")
                    return None

                task_id = json_resp['taskId']

                ready = False
                iterations = 0
                while not ready:
                    await asyncio.sleep(5)
                    ss = int((datetime.datetime.now() - self.started_at).total_seconds())
                    logger.info(f"Checking on task: time elapsed: {ss}s")

                    async with session.post("https://api.anti-captcha.com/getTaskResult", json={
                        "clientKey": ANTI_CAPTCHA_KEY, "taskId": task_id
                    }) as response:
                        json_resp = await response.json()
                        ready = json_resp['status'] == 'ready'
                        if ready:
                            logger.info("Got solution")
                        else:
                            logger.info("Solution is not ready yet")

                    iterations += 1

                    if iterations > 30:
                        logger.error("Could not receive solution in 30 iterations.")
                        return None

                self.finished_at = datetime.datetime.now()
                return json_resp['solution']['gRecaptchaResponse']


async def update_users(users):
    for user in users:
        last_processed = int(user['last_processed_day']))

        if last_processed == datetime.datetime.now().day:
            continue

        username = user['name']

        solution = CaptchaSolver()
        captcha = await solution.solve()
        if captcha is None:
            logger.error("Captcha not solved. Skip voting")
            return

        logger.info(f"Captcha took {solution.get_solution_time()}")

        async with aiohttp.ClientSession() as session:
            async with session.get("https://minecraft-server-list.com/server/218820/vote/") as response:
                html = await response.text()
                soup = BeautifulSoup(html, features='html.parser')
                form = soup.find('form', {'id': 'voteform'})
                ipennn = form.find('input', {'name': 'ipennn'}).get('value')
                iden = form.find('input', {'name': 'iden'}).get('value')
                voteses = re.search(r'saveVote\((.*)\);', html).group(1)

            logger.info(
                f"Sending a request:\n"
                f"ipennn: {ipennn}\n"
                f"iden: {iden}\n"
                f"voteses: {voteses}\n"
                f"ignn: {username}\n"
                f"cookies: {' '.join([f'{cookie.key}={cookie.value}' for cookie in session.cookie_jar])}\n"
                f"captcha: {captcha}"
            )

            async with session.post(f"https://minecraft-server-list.com/servers/voter10.php?voteses={voteses}", data={
                "ipennn": ipennn,
                "iden": iden,
                "ignn": username,
                "g-recaptcha-response": captcha

            }, headers=HEADERS) as response:
                try:
                    json_data = json.loads(await response.text())
                except:
                    logger.error(f"Response is not json:\n\n{await response.text()}")
                    return

                if 'error' in json_data:
                    logger.error(f"Vote request failed: {json_data}")
                else:
                    logger.info(f"Vote result: {json_data}")
                    user['last_processed'] = datetime.datetime.now().day


async def main():
    while True:

        with open('data.json', 'r') as f:
            users = json.load(f)

        try:
            await update_users(users)
        except:
            logger.exception("Error while updating users")

        with open('data.json', 'w') as f:
            json.dump(users, f)

        time.sleep(int(os.environ.get('VOTE_DELAY', 60)))

asyncio.get_event_loop().run_until_complete(main())
