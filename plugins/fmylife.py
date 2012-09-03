from util import hook, http

from bs4 import BeautifulSoup

fml_cache = []


def refresh_cache():
    """ gets a page of random FMLs and puts them into a dictionary """
    page = http.get('http://www.fmylife.com/random/')
    soup = BeautifulSoup(page, 'lxml')

    for e in soup.find_all('div', {'class': 'post article'}):
        id = int(e['id'])
        text = ''.join(e.find('p').find_all(text=True))
        text = http.unescape(text)
        fml_cache.append((id, text))

# do an initial refresh of the cache
refresh_cache()


@hook.command(autohelp=False)
def fml(inp, reply=None):
    "fml -- Gets a random quote from fmyfife.com."

    # grab the last item in the fml cache and remove it
    id, text = fml_cache.pop()
    # reply with the fml we grabbed
    reply('(#%d) %s' % (id, text))
    # refresh fml cache if its getting empty
    if len(fml_cache) < 3:
        refresh_cache()
