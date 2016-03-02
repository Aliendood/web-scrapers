import sys
import os
wd = os.path.abspath('.')
sys.path.append(wd + '/../')
import multiprocessing
import datetime
import pytz
from functools import partial
from general_utilities.query_utilities import format_query, get_html
from general_utilities.storage_utilities import store_in_mongo
from general_utilities.parsing_utilities import parse_num
from request_threading import RequestInfoThread

def multiprocess_pages(base_URL, job_title, job_location, page_number): 
    """Grab the URLS and other relevant info. from job postings on the page. 

    The Simply Hired URL used for job searching takes another parameter, 
    `pn`, that allows you to start the job search at jobs 11-20, 
    21-30, etc. I can use this to grab job results from multiple pages at
    once. This function takes in the base_URL and then adds that
    pn={page_number} parameter to the URL, and then queries it. 
    It passes the results on to a thread to grab the details from each
    job posting.

    Args: 
        base_URL: String that holds the base URL to add the page_start 
            parameter to. 
        job_title: String holding the job title used for the search
        job_location: String holding the job location used for the search 
        page_number: Integer of what the `start` parameter in the URL should
            be set to. 
    """

    url = base_URL + '&pn=' + str(page_number)
    html = get_html(url)
    # Each row corresponds to a job. 
    jobs = html.select('.js-job')
    threads = []
    mongo_update_lst = []
    for job in jobs: 
        thread = RequestInfoThread(job, job_title, job_location)
        thread.start()
        threads.append(thread)
    for thread in threads: 
        thread.join()
        mongo_update_lst.append(thread.json_dct)
    
    store_in_mongo(mongo_update_lst, 'job_postings', 'simplyhired')

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

    base_URL = 'http://www.simplyhired.com/search?'
    query_parameters = ['q={}'.format('+'.join(job_title.split())), 
            '&l={}'.format('+'.join(job_location.split())), '&mi={}'.format(radius),
            '&fdb=5', '&clst=CTL']
    
    query_URL = format_query(base_URL, query_parameters)

    # Get HTML for base query
    html = get_html(query_URL)
    try: 
        num_jobs_txt = str(html.select('.result-headline')[0].text)
        num_jobs = int(parse_num(num_jobs_txt, 2))
    except: 
        print 'No jobs for search {} in {}'.format(job_title, job_location)
        sys.exit(0)

    current_date = str(datetime.datetime.now(pytz.timezone('US/Mountain')))
    storage_dct = {'job_site': 'simplyhired', 'num_jobs': num_jobs, 
            'date': current_date, 'title': job_title, 'location': job_location}
    store_in_mongo([storage_dct], 'job_numbers', 'simplyhired')

    # Now we need to cycle through all of the job postings that we can 
    # and grab the url pointing to it, to then query it. All of the jobs
    # should be available through the '.js-job-link' class.
    max_pages = num_jobs / 10 + 1
    page_numbers = range(1, max_pages + 1)
    execute_queries = partial(multiprocess_pages, query_URL, job_title, 
            job_location)
    pool = multiprocessing.Pool(multiprocessing.cpu_count())
    pool.map(execute_queries, page_numbers)
