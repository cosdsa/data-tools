"""Maps addresses from a CSV to Colorado Springs City Council Districts.

Uses ArcGIS data from the map on this site: https://coloradosprings.gov/CityCouncilDistricts

This program is most accurate if the address column contains only street addresses, and only
addresses within Colorado Springs.

1. Takes in the filepath for a CSV that includes street address information and the name of the
   address column.
2. Evaluates addresses against city council district ArcGIS map.
3. Adds four columns to the data:
    a. Address Matched: The ArcGIS address that was matched to the given address
    b. Address Match Score: ArcGIS provided 0-100 confidence interval on a correct address match
    c. City Council District: The numeric Colorado Springs city council district
    d. Councilmember Name: The current sitting councilmember for the assigned district
4. Exports the augmented data to a new CSV file with all original columns plus new columns and saves
   the file to the folder of the user's choosing. 
"""

from arcgis.gis import GIS
from arcgis.features import FeatureLayer
from arcgis.geocoding import Geocoder, geocode
from arcgis.geometry.filters import intersects
import pandas as pd
from datetime import datetime
from tqdm import tqdm

def get_city_council_district_server_url(gis: GIS, config: dict):
    # Find the FeatureLayer that contains city council districts - this also is unlikely to be exactly 
    # repeatable for other maps. Recommend manually scrubbing through the webmap_data to locate the URL
    webmap_id = config["values"]["webmap"]
    webmap_data = gis.content.get(webmap_id).get_data()
    layers = webmap_data["operationalLayers"][0]["layers"]
    for layer in layers:
        if layer["title"] == "Council Districts (Identify)":
            city_council_district_server_url = layer["url"]
    # print(f"City Council District Server URL: {city_council_district_server_url}")
    return city_council_district_server_url

def get_address_lookup_server_url(config: dict):
    # URL for the arcgis lookup functionality. Does not include map-specific metadata, but allows for
    # address locating which can be later paired with map-specific metadata
    # I output the config JSON and manually looked through it to find the URL. Not sure if the
    # structure is repeatable for other maps
    address_lookup_server_url = config["values"]["searchConfiguration"]["sources"][0]["url"]
    # print(f"Address Lookup Server URL: {address_lookup_server_url}")
    return address_lookup_server_url

def find_district(address: str, locator: Geocoder, districts: FeatureLayer, council_district_fields: list):
    address_results = geocode(address, 
                   geocoder=locator, 
                   max_locations=1,
                   out_fields="*", # Selects all fields
                   out_sr=4326 # Returns latitude and longitude
                   )
    if not address_results:
        return {"input": address, "matched": None, "score": None}

    # Gets latitude and longitude to feed into district map
    loc = address_results[0]["location"]

    # Finds council district
    result = districts.query(
        geometry_filter=intersects(loc, sr=4326),
        out_fields=",".join(council_district_fields),
        return_geometry=False,
    )
    council_district_attrs = result.features[0].attributes if result.features else {}
    return {"input": address, "matched": address_results[0]["address"],
            "score": address_results[0]["score"], **council_district_attrs}


def main():
    print("What is the full file path with your address data CSV?")
    addresses_file_path = input()
    print("What is the name of the column with the addresses? This is case and space sensitive.")
    address_column_name = input()
    print("What is the full path of the folder that you want your augmented data saved to?")
    output_folder = input()
    
    # Found this by inspecting the webpage with the arcgis map
    # (https://coloradosprings.gov/CityCouncilDistricts)
    map_url = "https://coloradosprings.maps.arcgis.com/apps/instant/lookup/index.html?appid=80dd133159bc4ddb8b82988b1ad797ed"
    # Isolate the app id - this needs to be updated if there are other query parameters
    app_id = map_url.split("appid=")[1]

    # Create a gis object - works for maps with public access
    gis = GIS() 
    # Overall map object, for further parsing later on
    app = gis.content.get(app_id)

    # Gets the JSON config of the map
    config = app.get_data()

    city_council_district_server_url = get_city_council_district_server_url(gis, config)
    address_lookup_server_url = get_address_lookup_server_url(config)

    # Create gis objects for searching
    locator = Geocoder(address_lookup_server_url, gis)
    districts = FeatureLayer(city_council_district_server_url)

    # Find fields for districts map - manually selected which ones I wanted for the next step
    # To select more fields, uncomment this block to see the field options
    print([(f["name"], f["type"]) for f in districts.properties.fields])

    council_district_fields = ["DISTRICT", "NAME", "RepName"]
    
    addresses_data = pd.read_csv(addresses_file_path).to_dict(orient="records")
    print("Evaluating records...")
    for i, record in tqdm(enumerate(addresses_data)):
        address = record[address_column_name]
        council_district = find_district(address, locator, districts, council_district_fields)
        record["Address Matched"] = council_district.get("matched")
        record["Address Match Score"] = council_district.get("score")
        record["City Council District"] = council_district.get("DISTRICT")
        record["Councilmember Name"] = council_district.get("RepName")
        addresses_data[i] = record
    
    augmented_data = pd.DataFrame.from_records(addresses_data)
    now = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    augmented_file_name = f"{output_folder}\\address_data_city_council_district_{now}.csv"
    
    augmented_data.to_csv(augmented_file_name, index=False)
    
if __name__ == "__main__":
    main()
