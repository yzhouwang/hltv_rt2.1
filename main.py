import cloudscraper
from bs4 import BeautifulSoup
import csv
import time

def scrape_results_page(offset):
    """
    Scrapes the results page for a given offset and returns a list of full match URLs.
    """
    url = f"https://www.hltv.org/results?offset={offset}"
    scraper = cloudscraper.create_scraper()
    response = scraper.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    
    match_urls = []
    # Each match result is wrapped in a div with class "result-con"
    for result_con in soup.find_all("div", class_="result-con"):
        anchor = result_con.find("a", class_="a-reset")
        if anchor:
            relative_url = anchor.get("href", "")
            # Build the full URL if the link is relative
            if relative_url.startswith("/"):
                full_url = "https://www.hltv.org" + relative_url
            else:
                full_url = relative_url
            match_urls.append(full_url)
    return match_urls

def scrape_all_matches():
    """
    Iterates over results pages from offset 0 to 1000 (each page having 100 matches),
    calls your pre-existing scrape_match_stats for each match URL,
    and compiles the data into a list.
    """
    all_match_stats = []
    
    # Iterate over offsets: 0, 100, 200, …, 1000
    for offset in range(0, 1100, 100):
        print(f"Scraping results page with offset {offset}...")
        match_urls = scrape_results_page(offset)
        print(f"Found {len(match_urls)} matches on page {offset}.")
        for url in match_urls:
            print(f"Scraping match stats for: {url}")
            try:
                # Call your already defined function; it returns a dict with match stats
                stats = scrape_match_stats(url)
                # Optionally, add the match URL into the stats for reference
                stats["match_url"] = url
                all_match_stats.append(stats)
            except Exception as e:
                print(f"Error scraping {url}: {e}")
            # Be polite to the server
            time.sleep(1)
    return all_match_stats

def scrape_match_stats(url):
    scraper = cloudscraper.create_scraper()
    response = scraper.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # ---- Locate the main matchstats container ----
    match_stats_div = soup.find("div", class_="matchstats")
    if not match_stats_div:
        print("No matchstats found.")
        return {}

    # We'll parse the 'all-content' tab (All maps). 
    # If you want each map separately, you'd loop over each "div.stats-content" with different IDs.
    all_content_div = match_stats_div.find("div", id="all-content")
    if not all_content_div:
        print("No 'All maps' content found.")
        return {}

    # This will hold everything we extract from "all-content"
    all_content_data = {
        "teamStats": []  # list of teams, each with a list of players
    }

    # Inside all-content, HLTV has multiple tables:
    #   1) table.totalstats
    #   2) table.ctstats
    #   3) table.tstats
    # for each team
    tables = all_content_div.find_all("table", recursive=False)  
    # Note: We use recursive=False so we only get immediate tables, not nested ones from submaps.

    # Each table has:
    # - The header row with the team name and columns
    # - Several player rows
    # There's usually a "header-row" <tr> that contains the team name (within <div class="align-logo">).
    
    for table in tables:
        # Identify if it’s totalstats, ctstats, or tstats:
        table_class = " ".join(table.get("class", []))  # e.g. "table totalstats"

        # The first <tr> with class="header-row" holds the team name
        header_tr = table.find("tr", class_="header-row")
        if not header_tr:
            continue

        # Extract the team name
        team_name_el = header_tr.find("a", class_="teamName")  
        if not team_name_el:
            # fallback
            team_name = "Unknown"
        else:
            team_name = team_name_el.get_text(strip=True)

        # Next, gather all <tr> that are the player rows
        # They typically have class="" or some variation, but not "header-row"
        # So let's find all <tr> except the header-row:
        player_rows = table.find_all("tr", class_=lambda c: c == "")

        # We'll store the results in a structure
        team_stats = {
            "teamName": team_name,
            "tableType": table_class,  # e.g. "table totalstats" or "table ctstats"
            "players": []
        }

        for row in player_rows:
            # Each player row typically has these columns:
            #   [0]: player's info (flagAlign, link, name)
            #   [1]: "K-D"
            #   [2]: "+/-"
            #   [3]: "ADR"
            #   [4]: "KAST"
            #   [5]: "Rating"
            cols = row.find_all("td")
            if len(cols) < 6:
                continue

            # Player link & name
            player_link = cols[0].find("a", href=True)
            player_name = "N/A"
            if player_link:
                # There's typically a <div class="gtSmartphone-only statsPlayerName"> with text: "Firstname 'nick' Lastname"
                # or for smaller devices: <div class="smartphone-only statsPlayerName">...
                # We'll just get the anchor text or the next nested element:
                # In the snippet, anchor text is something like jks + the hidden real name. 
                # You could parse them differently if you want the real name vs. handle.
                # For simplicity, let's just use the anchor's text
                player_name = player_link.get_text(strip=True)

            kd        = cols[1].get_text(strip=True)
            plus_minus= cols[2].get_text(strip=True)
            adr       = cols[3].get_text(strip=True)
            kast      = cols[4].get_text(strip=True)
            rating    = cols[5].get_text(strip=True)

            # Save player data
            player_data = {
                "player": player_name,
                "kd": kd,
                "plus_minus": plus_minus,
                "adr": adr,
                "kast": kast,
                "rating": rating
            }
            team_stats["players"].append(player_data)

        # Add this table’s data to the final structure
        all_content_data["teamStats"].append(team_stats)

    return all_content_data


def save_to_csv(data, filename):
    """
    Flattens the nested match stats structure and saves the data into a CSV file.
    
    In this example, each row in the CSV corresponds to a player entry,
    along with associated team and match info.
    """
    rows = []
    for match in data:
        match_url = match.get("match_url", "")
        for team in match.get("teamStats", []):
            team_name = team.get("teamName", "")
            table_type = team.get("tableType", "")
            for player in team.get("players", []):
                row = {
                    "match_url": match_url,
                    "teamName": team_name,
                    "tableType": table_type,
                    "player": player.get("player", ""),
                    "kd": player.get("kd", ""),
                    "plus_minus": player.get("plus_minus", ""),
                    "adr": player.get("adr", ""),
                    "kast": player.get("kast", ""),
                    "rating": player.get("rating", "")
                }
                rows.append(row)
    
    fieldnames = ["match_url", "teamName", "tableType", "player", "kd", "plus_minus", "adr", "kast", "rating"]
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Data saved to {filename}")

if __name__ == "__main__":
    # Scrape match stats from all results pages (offset 0 to 1000)
    all_match_stats = scrape_all_matches()
    # Save the collected data into a CSV file
    save_to_csv(all_match_stats, "match_stats.csv")
