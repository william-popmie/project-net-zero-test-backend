from codecarbon import EmissionsTracker
import math

def heavy_compute():
    """Something CPU-intensive enough to measure."""
    result = 0
    for i in range(1, 5_000_000):
        result += math.sqrt(i) * math.log(i)
    return result

def main():
    print("Starting CodeCarbon tracking...\n")

    with EmissionsTracker(project_name="net-zero-test") as tracker:
        result = heavy_compute()

    emissions = tracker.final_emissions          # kg CO2eq
    emissions_data = tracker.final_emissions_data

    print(f"Compute result:       {result:.2f}")
    print(f"Emissions:            {emissions * 1000:.6f} g CO2eq")
    print(f"Energy consumed:      {emissions_data.energy_consumed * 1000:.4f} Wh")
    print(f"Duration:             {emissions_data.duration:.2f} s")
    print(f"Country:              {emissions_data.country_name}")
    carbon_intensity = emissions / emissions_data.energy_consumed * 1000  # gCO2/kWh
    print(f"Carbon intensity:     {carbon_intensity:.1f} gCO2/kWh")
    print(f"\nOutput saved to:      ./codecarbon-output/")

if __name__ == "__main__":
    main()
