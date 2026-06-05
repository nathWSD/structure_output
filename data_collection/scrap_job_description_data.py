import requests
from bs4 import BeautifulSoup
import json
import time
import urllib.parse

BASE_SEARCH_URL = "https://www.jobbank.gc.ca/jobsearch/jobsearch?searchstring="
BASE_DOMAIN = "https://www.jobbank.gc.ca"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

JOB_TITLES = [
    "Software Engineer", "Software Developer", "Full Stack Developer",
    "Backend Developer", "Frontend Developer", "Data Scientist",
    "Machine Learning Engineer", "AI Engineer", "DevOps Engineer",
    "Cloud Engineer", "Data Analyst", "Business Intelligence Analyst",
    "QA Engineer", "Test Automation Engineer", "iOS Developer",
    "Android Developer", "UI Designer", "UX Designer", "Product Designer",
    "Cybersecurity Analyst", "Python Developer", "Data Engineer",
    "Network Engineer", "Cloud Architect", "Systems Engineer",
    "Java Developer", ".NET Developer", "Web Developer", "SDET",
    "Solutions Architect", "Big Data Specialist", "Fintech Engineer",
    "AI Prompt Engineer", "Blockchain Developer", "Robotics Engineer",
    "Javascript Developer", "AR Developer", "VR Developer",
    "IoT Engineer", "Ethical Hacker", "SRE", "Game Developer",
    "Product Manager", "Project Manager", "Marketing Specialist",
    "Digital Marketing Specialist", "SEO Specialist", "Content Writer",
    "Copywriter", "Business Analyst", "Operations Manager",
    "Sales Executive", "Technical Writer", "Market Research Analyst",
    "Graphic Designer"
]

def get_job_links(job_title, max_links=10):
    """Search JobBank for a job title and return up to max_links posting URLs."""
    encoded = urllib.parse.quote(job_title)
    url = BASE_SEARCH_URL + encoded

    print(f"\n🔍 Searching for: {job_title}")
    response = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(response.text, "html.parser")

    links = []
    for a in soup.select("a.resultJobItem"):
        href = a.get("href")
        if href and "jobposting" in href:
            full_url = BASE_DOMAIN + href
            links.append(full_url)
            if len(links) >= max_links:
                break

    print(f"➡ Found {len(links)} postings")
    return links


def scrape_job_page(url):
    """Scrape the full job description page from a given URL."""
    print(f"   📄 Scraping: {url}")
    response = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(response.text, "html.parser")

    # Extract the entire page text
    full_text = soup.get_text(separator="\n", strip=True)

    # Extract title
    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "Unknown Title"

    return {
        "url": url,
        "title": title,
        "full_page_text": full_text
    }


def main():
    output_file = open("jobbank_jobs.jsonl", "w", encoding="utf-8")

    for job in JOB_TITLES:
        links = get_job_links(job, max_links=7)

        if len(links) == 0:
            print(f"   ⚠ No postings found for {job}, skipping.")
            continue

        for link in links:
            data = scrape_job_page(link)
            output_file.write(json.dumps(data, ensure_ascii=False) + "\n")
            time.sleep(1)  # polite delay

        time.sleep(2)  # delay between job titles

    output_file.close()
    print("\n🎉 Done! Saved to jobbank_jobs.jsonl")


if __name__ == "__main__":
    main()
