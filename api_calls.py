import requests 

url = 'http://export.arxiv.org/api/query?search_query=all:electron&start=0&max_results=5'

def make_query(url):
    response = requests.get(url)

    if response:
        print(response.content)
    else:
        raise Exception(f"Unsuccessful API usage: {response.status_code}")

