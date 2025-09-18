# earthquake_monitor.py (Harita HTML Üretimi Düzeltildi)
"""
Simple Earthquake Monitor
Lightweight earthquake monitoring for web interface
"""

import requests
import time
from datetime import datetime
from typing import List, Dict, Any
from bs4 import BeautifulSoup
import logging
import folium
from branca.element import Figure # Import Figure for better HTML handling

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EarthquakeMonitor:
    """Simplified earthquake monitoring for web interface"""
    
    def __init__(self):
        self.kandilli_url = "http://www.koeri.boun.edu.tr/scripts/lst5.asp"
        self.is_monitoring = False
        self.last_check: float = 0
        self.earthquakes: List[Dict[str, Any]] = []
        self.max_earthquakes = 50
    
    def start_monitoring(self):
        """Start earthquake monitoring"""
        self.is_monitoring = True
        logger.info("Earthquake monitoring started")
    
    def stop_monitoring(self):
        """Stop earthquake monitoring"""
        self.is_monitoring = False
        logger.info("Earthquake monitoring stopped")
    
    def get_recent_earthquakes(self) -> List[Dict[str, Any]]:
        """Get recent earthquakes from Kandilli"""
        if not self.is_monitoring:
            return self.earthquakes
        
        try:
            if (time.time() - self.last_check) < 30:
                return self.earthquakes
            
            response = requests.get(self.kandilli_url, timeout=10)
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            pre_tag = soup.find('pre')
            
            if not pre_tag:
                logger.warning("Could not find earthquake data in response")
                return self.earthquakes
            
            earthquake_data = pre_tag.text.strip()
            lines = earthquake_data.splitlines()
            
            new_earthquakes = []
            
            for line in lines[7:]:
                line = line.strip()
                if not line or len(line.split()) < 10:
                    continue
                
                try:
                    parts = line.split()
                    date_str = parts[0]
                    time_str = parts[1]
                    latitude = float(parts[2])
                    longitude = float(parts[3])
                    depth = float(parts[4])
                    magnitude = float(parts[6])
                    location = ' '.join(parts[9:])
                    
                    earthquake = {
                        'time': f"{date_str} {time_str}",
                        'latitude': latitude,
                        'longitude': longitude,
                        'depth': depth,
                        'magnitude': magnitude,
                        'location': location,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    new_earthquakes.append(earthquake)
                    
                except (ValueError, IndexError) as e:
                    logger.debug(f"Could not parse earthquake line: {line} - {e}")
                    continue
            
            self.earthquakes = new_earthquakes[:self.max_earthquakes]
            self.last_check = time.time()
            
            logger.debug(f"Retrieved {len(new_earthquakes)} earthquakes from Kandilli")
            return self.earthquakes
            
        except Exception as e:
            logger.error(f"Error fetching earthquake data: {e}")
            return self.earthquakes
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get monitoring status"""
        return {
            'is_monitoring': self.is_monitoring,
            'last_check': self.last_check,
            'earthquake_count': len(self.earthquakes),
            'last_update': datetime.now().isoformat()
        }

    def get_earthquake_dataframe(self):
        """Get earthquakes as a DataFrame for Gradio"""
        import pandas as pd
        if not self.earthquakes:
            return pd.DataFrame(columns=['Tarih/Saat', 'Büyüklük (ML)', 'Derinlik (km)', 'Konum', 'Enlem', 'Boylam'])
        
        df = pd.DataFrame(self.earthquakes)
        df_display = df[['time', 'magnitude', 'depth', 'location', 'latitude', 'longitude']]
        df_display.columns = ['Tarih/Saat', 'Büyüklük (ML)', 'Derinlik (km)', 'Konum', 'Enlem', 'Boylam']
        return df_display

    def get_folium_map_html(self):
        """Generate and return the Folium map as an HTML string."""
        # Create a Figure to hold the map
        fig = Figure(width="100%", height=600)
        
        if not self.earthquakes:
            m = folium.Map(location=[39.9334, 32.8597], zoom_start=6, tiles="CartoDB positron")
            folium.Marker(
                [39.9334, 32.8597],
                popup="Veri yok. Lütfen daha sonra tekrar deneyin.",
                icon=folium.Icon(color='red', icon='info-sign')
            ).add_to(m)
            # Add map to figure
            fig.add_child(m)
            return fig._repr_html_() # Return HTML representation of the figure

        m = folium.Map(location=[39.9334, 32.8597], zoom_start=6, tiles="CartoDB positron")

        for eq in self.earthquakes:
            popup_text = f"""
            <b>Tarih/Saat:</b> {eq['time']}<br>
            <b>Büyüklük:</b> {eq['magnitude']} ML<br>
            <b>Derinlik:</b> {eq['depth']} km<br>
            <b>Konum:</b> {eq['location']}<br>
            <b>Enlem:</b> {eq['latitude']}<br>
            <b>Boylam:</b> {eq['longitude']}
            """
            
            marker_radius = max(3, eq['magnitude'] * 3)
            
            folium.CircleMarker(
                location=[eq['latitude'], eq['longitude']],
                radius=marker_radius,
                popup=folium.Popup(popup_text, max_width=300),
                color='red',
                fill=True,
                fillColor='red',
                fillOpacity=0.6
            ).add_to(m)
            
        # Add map to figure
        fig.add_child(m)
        # Return the HTML representation of the figure
        return fig._repr_html_()

# Global instance for the app
earthquake_monitor = EarthquakeMonitor()
earthquake_monitor.start_monitoring()