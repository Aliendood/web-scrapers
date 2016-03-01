import sys
import os
wd = os.path.abspath('.')
sys.path.append(wd + '/../')
import multiprocessing
import datetime
from functools import partial
from pymongo import MongoClient
from general_utilities.query_utilities import get_html, format_query
from general_utilities.storage_utilities import store_in_mongo
from general_utilities.parsing_utilities import parse_num
from request_threading import RequestInfoThread 

def multiprocess_pages(base_URL, job_title, job_location, page_start): 
    """Grab the URLS and other relevant info. from job postings on the page. 

    The Indeed URL used for job searching takes another parameter, 
    `start`, that allows you to start the job search at jobs 10-20, 
    20-30, etc. I can use this to grab job results from multiple pages at
    once. This function takes in the base_URL and then adds that
    start={page_start} parameter to the URL, and then queries it. 
    It passes the results on to a thread to grab the details from each
    job posting.

    Args: 
        base_URL: String that holds the base URL to add the page_start 
            parameter to. 
        job_title: String holding the job title used for the search
        job_location: String holding the job location used for the search 
        page_start: Integer of what the `start` parameter in the URL should
            be set to. 
    """

    url = base_URL + '&start=' + str(page_start)
    html = get_html(url)
    # Each row corresponds to a job. 
    rows = html.select('.row')
    threads = []
    mongo_update_lst = []
    for row in rows: 
        thread = RequestInfoThread(row, job_title, job_location)
        thread.start()
        threads.append(thread)
    for thread in threads: 
        thread.join()
        mongo_update_lst.append(thread.json_dct)

    store_in_mongo(mongo_update_lst, 'job_postings', 'indeed')

if __name__ == '__main__':
    # I expect that at the very least a job title, job location, and radius
    # will be passed in, so I'll attempt to get both of those within
    # a try except and throw an error otherwise. 
    try: 
        job_title = sys.argv[1]
        job_location = sys.argv[2]
        radius = sys.argv[3]
    except IndexError: 
        raise Exception('Program needs a job title, job location, and radius inputted!')

    base_URL = 'https://www.indeed.com/jobs?'
    query_parameters = ['q={}'.format('+'.join(job_title.split())),
            '&l={}'.format('+'.join(job_location.split())), '&radius={}'.format(radius), 
            '&sort=date', '&fromage=5']

    query_URL = format_query(base_URL, query_parameters)

    # Get HTML for base query.
    html = get_html(query_URL)
    num_jobs_txt = str(html.select('#searchCount'))
    num_jobs = int(parse_num(num_jobs_txt, 2))
    current_date = datetime.date.today().strftime("%m-%d-%Y")
    storage_dct = {'job_site': 'indeed', 'num_jobs': num_jobs, 
            'date': current_date, 'title': job_title, 'location': job_location}
    store_in_mongo([storage_dct], 'job_numbers', 'indeed')

    # Now we need to cycle through all of the job postings that we can and 
    # grab the url pointing to it, to then query it. All of the jobs should 
    # be available via the .turnstileLink class, and then the href attribute
    # will point to the URL. I'm going to multiprocess and multithread this.  
    max_start_position = 1000 if num_jobs >= 1000 else num_jobs
    # I'll need to be able to pass an iterable to the multiprocessing pool. 
    start_positions = range(0, max_start_position, 10)
    execute_queries = partial(multiprocess_pages, query_URL, \
            job_title, job_location)
    pool = multiprocessing.Pool(multiprocessing.cpu_count())
    pool.map(execute_queries, start_positions)
