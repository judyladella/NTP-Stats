import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def load_and_label(filename, region_label):
    try:
        conn = sqlite3.connect(filename)
        df = pd.read_sql_query("SELECT * FROM ntp_metrics", conn)
        conn.close()
        df['region'] = region_label
        return df
    except Exception as e:
        print(f"Could not load {filename}: {e}")
        return pd.DataFrame()

def plot_ntp_research():
    # 1. Load both datasets
    df_east = load_and_label('research_data_east.db', 'East (Michigan)')
    df_west = load_and_label('research_data_west.db', 'West (San Diego)')
    
    df = pd.concat([df_east, df_west], ignore_index=True)

    if df.empty:
        print("No data found in either database.")
        return

    df['recorded_at'] = pd.to_datetime(df['recorded_at'])
    plt.figure(figsize=(14, 8))
    
    # 2. Plot by Region and Protocol
    for region in df['region'].unique():
        region_data = df[df['region'] == region]
        
        # Plot Custom UDP Measurements
        custom = region_data[region_data['protocol_type'] == 'CUSTOM_UDP']
        plt.plot(custom['recorded_at'], custom['offset_sec'], 
                 label=f"Custom UDP ({region})", alpha=0.8)

        # Plot Standard NTP for reference
        std = region_data[region_data['protocol_type'] == 'STANDARD_NTP']
        if not std.empty:
            plt.scatter(std['recorded_at'], std['offset_sec'], 
                        s=10, label=f"External NTP ({region})", alpha=0.4)

    plt.axhline(y=0, color='red', linestyle='--', alpha=0.3)
    plt.title('CMPM118 Research: Comparative Network Latency (East vs West)', fontsize=14)
    plt.ylabel('Clock Offset (Seconds)')
    plt.xlabel('Time (UTC)')
    plt.legend(loc='upper right', bbox_to_anchor=(1.2, 1))
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    plot_ntp_research()