import React, { useState } from 'react';
import { runConciergeStream, parseMarkdownToRecommendations } from './api/client';
import './App.css';
import { 
  Sparkles, 
  AlertTriangle,
  Calendar,
  Activity,
  Check,
  MapPin,
  ExternalLink,
  Phone,
  Clock,
  Compass
} from 'lucide-react';

export interface Facility {
  id: string;
  name: string;
  address: string;
  phone: string;
  website: string;
  rating: number;
  coordinates: {
    lat: number;
    lng: number;
  };
  amenities: string[];
  emoji_badges: string[];
  pricing: {
    access_type: string;
    cost: number | null;
    pass_detail: string;
  };
  hours: {
    open: string;
    close: string;
    warning: string | null;
    pool_hours: string | null;
  };
  distance: {
    value_miles: number;
    walking_time_minutes: number;
    transit_time_minutes: number;
    description: string;
  };
  reviews_summary: string;
  crowd_warning: string | null;
  recommendation_metadata: {
    best_for: string;
    limitations: string;
  };
}

export interface Recommendation {
  facility: Facility;
  rank: number;
  match_quality: 'Excellent Match' | 'Good Alternative' | 'Limited Match';
  recommendation_reason: string;
  eligibility_status: 'Fits Your Criteria' | 'Alternative' | 'Rejected';
  card_summary: string;
  badge_subtitle: string;
  
  // Canonical source of truth fields
  id?: string;
  place_id?: string;
  name?: string;
  address?: string;
  coordinates?: { lat: number; lng: number };
  rating?: number;
  walk_minutes?: number;
  drive_minutes?: number;
  effective_price?: number | null;
  access_type?: string;
  amenities?: string[];
  google_maps_url?: string;
  phone_number?: string;
  website?: string;
  official_website_url?: string;
  photo_url?: string;
  photo_source?: string;
  opening_hours_summary?: string;
  is_open_now?: boolean;
  pool_hours?: string;
  facility_hours?: string;
  display_name?: string;
  validation_status?: string;
  confidence?: number;
  explanation?: string;
  access_status?: 
    | "verified_member_access"
    | "verified_day_pass"
    | "free_public_access"
    | "unknown"
    | "membership_required"
    | "rejected";
  access_source?: string;
  membership_evidence?: string;
  access_warnings?: string[];
  amenity_states?: Record<string, "verified" | "unknown" | "unavailable">;
  amenity_sources?: Record<string, string>;
}

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  public state: ErrorBoundaryState = {
    hasError: false
  };

  public static getDerivedStateFromError(_: Error): ErrorBoundaryState {
    return { hasError: true };
  }

  public componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary caught an error in dashboard rendering:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div style={{ 
          padding: '24px', 
          textAlign: 'center', 
          border: '1.5px dashed #ef4444', 
          background: '#fef2f2', 
          borderRadius: '12px', 
          margin: '20px 0',
          boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
          maxWidth: '600px',
          marginLeft: 'auto',
          marginRight: 'auto'
        }}>
          <span style={{ fontSize: '2.5rem' }}>⚠️</span>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 800, color: '#991b1b', margin: '12px 0 6px 0' }}>Render Error</h3>
          <p style={{ fontSize: '0.85rem', color: '#7f1d1d', margin: 0, fontWeight: 500 }}>
            TravelWell received a response, but could not render it.
          </p>
          <button 
            onClick={() => this.setState({ hasError: false })}
            style={{ 
              marginTop: '14px', 
              background: '#dc2626', 
              color: '#ffffff', 
              border: 'none', 
              padding: '8px 16px', 
              borderRadius: '6px', 
              fontWeight: 700, 
              cursor: 'pointer',
              fontSize: '0.75rem',
              textTransform: 'uppercase',
              letterSpacing: '0.5px'
            }}
          >
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

const USER_FACILITIES_ELIGIBLE: Recommendation[] = [
  {
    rank: 1,
    match_quality: 'Excellent Match',
    eligibility_status: 'Fits Your Criteria',
    recommendation_reason: 'Chosen because it is fully covered by your YMCA membership reciprocity, features an indoor lap pool and modern treadmills, and is a convenient 10-minute walk.',
    card_summary: '✓ Free with your YMCA membership • 10-minute walk • Open until 10 PM',
    badge_subtitle: 'Highest overall score',
    facility: {
      id: 'ymca_chicago',
      name: 'Downtown Chicago YMCA',
      address: '30 S Michigan Ave, Chicago, IL 60603',
      phone: '+1 (312) 269-0500',
      website: 'https://www.ymcachicago.org',
      rating: 4.5,
      coordinates: { lat: 41.8812, lng: -87.6246 },
      amenities: ['pool', 'treadmill', 'showers', 'lockers'],
      emoji_badges: ['🏊 Pool', '🏃 Treadmill', '🚿 Showers', '🔒 Lockers'],
      pricing: {
        access_type: 'membership_reciprocity',
        cost: 0.0,
        pass_detail: 'Free access with national YMCA membership'
      },
      hours: {
        open: '06:00 AM',
        close: '10:00 PM',
        warning: null,
        pool_hours: '06:30 AM - 08:30 PM'
      },
      distance: {
        value_miles: 0.5,
        walking_time_minutes: 10,
        transit_time_minutes: 4,
        description: '0.5 miles'
      },
      reviews_summary: 'Clean facility, features an indoor lap pool and modern treadmills. Showers are clean, lockers available.',
      crowd_warning: 'Moderate crowd expected between 5:30 PM and 7:30 PM.',
      recommendation_metadata: {
        best_for: 'YMCA members looking for free lap swimming and gym access in the Loop.',
        limitations: 'Can become moderately busy during standard post-work rush hours.'
      }
    }
  },
  {
    rank: 2,
    match_quality: 'Excellent Match',
    eligibility_status: 'Fits Your Criteria',
    recommendation_reason: 'A premium option that meets all your preferences and constraints, including both an indoor pool and treadmills. Saline pool is top-tier.',
    card_summary: '✓ High rating • 18-minute walk • Open until 9 PM',
    badge_subtitle: 'Highest rating',
    facility: {
      id: 'ffc_union',
      name: 'Fitness Formula Club (FFC) Union Station',
      address: '444 W Jackson Blvd, Chicago, IL 60606',
      phone: '+1 (312) 906-9900',
      website: 'https://ffc.com/clubs/union-station',
      rating: 4.7,
      coordinates: { lat: 41.8781, lng: -87.6394 },
      amenities: ['pool', 'treadmill', 'showers', 'lockers', 'towels'],
      emoji_badges: ['🏊 Pool', '🏃 Treadmill', '🚿 Showers', '🔒 Lockers', '🧺 Towels'],
      pricing: {
        access_type: 'day_pass',
        cost: 20.0,
        pass_detail: '$20 guest pass available with local registration'
      },
      hours: {
        open: '05:00 AM',
        close: '09:00 PM',
        warning: null,
        pool_hours: '06:00 AM - 08:00 PM'
      },
      distance: {
        value_miles: 0.9,
        walking_time_minutes: 18,
        transit_time_minutes: 6,
        description: '0.9 miles'
      },
      reviews_summary: 'Premium club, excellent saline pool, top-tier treadmills, and high-end locker room facilities.',
      crowd_warning: 'Low crowding expected in the evening.',
      recommendation_metadata: {
        best_for: 'Premium workout experience with a high-end saline pool and excellent locker room facilities.',
        limitations: 'Price sits exactly at the maximum user budget limit.'
      }
    }
  },
  {
    rank: 3,
    match_quality: 'Good Alternative',
    eligibility_status: 'Fits Your Criteria',
    recommendation_reason: 'A budget-friendly option that meets your treadmill and shower requirements and is open 24 hours. Does not have an indoor pool.',
    card_summary: '✓ Lowest paid day pass • 22-minute walk • Open 24h',
    badge_subtitle: 'Lowest paid guest pass',
    facility: {
      id: 'planet_fitness_dt',
      name: 'Planet Fitness Downtown',
      address: '26 N Halsted St, Chicago, IL 60661',
      phone: '+1 (312) 207-1010',
      website: 'https://www.planetfitness.com',
      rating: 4.1,
      coordinates: { lat: 41.8821, lng: -87.6475 },
      amenities: ['treadmill', 'showers', 'lockers'],
      emoji_badges: ['🏃 Treadmill', '🚿 Showers', '🔒 Lockers'],
      pricing: {
        access_type: 'day_pass',
        cost: 10.0,
        pass_detail: '$10 day pass for non-members'
      },
      hours: {
        open: '00:00 AM',
        close: '11:59 PM',
        warning: null,
        pool_hours: null
      },
      distance: {
        value_miles: 1.2,
        walking_time_minutes: 22,
        transit_time_minutes: 7,
        description: '1.2 miles'
      },
      reviews_summary: 'Very cheap, open 24 hours. Good selection of treadmills. No pool.',
      crowd_warning: 'Moderate crowd expected.',
      recommendation_metadata: {
        best_for: 'Late-night treadmill runs on a low budget.',
        limitations: 'No pool (violates primary preference) and is located furthest from coordinates.'
      }
    }
  }
];

const USER_FACILITIES_IMPOSSIBLE: Recommendation[] = [
  {
    rank: 1,
    match_quality: 'Limited Match',
    eligibility_status: 'Alternative',
    recommendation_reason: 'Budget Cap Exceeded: Day pass cost of $10.0 exceeds your budget limit. It does meet your treadmill and shower preferences.',
    card_summary: '✓ 22-minute walk • Exceeds $5 budget cap',
    badge_subtitle: 'Lowest paid guest pass',
    facility: {
      id: 'planet_fitness_dt',
      name: 'Planet Fitness Downtown',
      address: '26 N Halsted St, Chicago, IL 60661',
      phone: '+1 (312) 207-1010',
      website: 'https://www.planetfitness.com',
      rating: 4.1,
      coordinates: { lat: 41.8821, lng: -87.6475 },
      amenities: ['treadmill', 'showers', 'lockers'],
      emoji_badges: ['🏃 Treadmill', '🚿 Showers', '🔒 Lockers'],
      pricing: {
        access_type: 'day_pass',
        cost: 10.0,
        pass_detail: '$10 day pass'
      },
      hours: {
        open: '00:00 AM',
        close: '11:59 PM',
        warning: null,
        pool_hours: null
      },
      distance: {
        value_miles: 1.2,
        walking_time_minutes: 22,
        transit_time_minutes: 7,
        description: '1.2 miles'
      },
      reviews_summary: 'Clean, cheap, open 24/7.',
      crowd_warning: 'Moderate crowd expected.',
      recommendation_metadata: {
        best_for: 'Standard treadmills.',
        limitations: 'Day pass is $10, which exceeds the budget limit.'
      }
    }
  },
  {
    rank: 2,
    match_quality: 'Limited Match',
    eligibility_status: 'Alternative',
    recommendation_reason: 'Budget Cap Exceeded: Day pass cost of $25.0 exceeds your budget limit. It includes an indoor pool, showers, and is a short 10-minute walk.',
    card_summary: '✓ 10-minute walk • Exceeds $5 budget cap',
    badge_subtitle: 'Pool & Treadmills included',
    facility: {
      id: 'ymca_chicago',
      name: 'Downtown Chicago YMCA',
      address: '30 S Michigan Ave, Chicago, IL 60603',
      phone: '+1 (312) 269-0500',
      website: 'https://www.ymcachicago.org',
      rating: 4.5,
      coordinates: { lat: 41.8812, lng: -87.6246 },
      amenities: ['pool', 'treadmill', 'showers', 'lockers'],
      emoji_badges: ['🏊 Pool', '🏃 Treadmill', '🚿 Showers', '🔒 Lockers'],
      pricing: {
        access_type: 'day_pass',
        cost: 25.0,
        pass_detail: '$25 day pass without membership'
      },
      hours: {
        open: '06:00 AM',
        close: '10:00 PM',
        warning: null,
        pool_hours: '06:30 AM - 08:30 PM'
      },
      distance: {
        value_miles: 0.5,
        walking_time_minutes: 10,
        transit_time_minutes: 4,
        description: '0.5 miles'
      },
      reviews_summary: 'Great loop gym, standard guest policies apply.',
      crowd_warning: 'Moderate crowd expected.',
      recommendation_metadata: {
        best_for: 'Loop gym access.',
        limitations: 'Price is over the requested budget.'
      }
    }
  }
];

declare global {
  interface Window {
    initGoogleMap?: () => void;
    google?: any;
  }
}

interface GoogleMapProps {
  apiKey: string;
  recommendations: Recommendation[];
  selectedId: string;
  onSelectId: (id: string) => void;
  showResults: boolean;
  resolvedLocation: { lat?: number; lng?: number; display_name?: string } | null;
}

function GoogleMapComponent({ apiKey, recommendations, selectedId, onSelectId, showResults, resolvedLocation }: GoogleMapProps) {
  const mapRef = React.useRef<HTMLDivElement>(null);
  const mapInstanceRef = React.useRef<any>(null);
  const markersRef = React.useRef<any[]>([]);
  const infoWindowRef = React.useRef<any>(null);

  React.useEffect(() => {
    if (window.google && window.google.maps) {
      initMap();
      return;
    }

    const script = document.createElement('script');
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&callback=initGoogleMap`;
    script.async = true;
    script.defer = true;
    document.head.appendChild(script);

    window.initGoogleMap = () => {
      initMap();
    };

    return () => {
      delete window.initGoogleMap;
    };
  }, [apiKey]);

  const initMap = () => {
    if (!mapRef.current || !window.google) return;
    mapInstanceRef.current = new window.google.maps.Map(mapRef.current, {
      center: { lat: 41.8817, lng: -87.6278 },
      zoom: 14,
      disableDefaultUI: true,
      zoomControl: true
    });
    infoWindowRef.current = new window.google.maps.InfoWindow();
  };

  React.useEffect(() => {
    if (!mapInstanceRef.current || !window.google) return;

    markersRef.current.forEach(m => m.setMap(null));
    markersRef.current = [];

    const bounds = new window.google.maps.LatLngBounds();
    const hotelPos = resolvedLocation && resolvedLocation.lat && resolvedLocation.lng
      ? { lat: resolvedLocation.lat, lng: resolvedLocation.lng }
      : { lat: 41.8817, lng: -87.6278 };
    bounds.extend(hotelPos);

    const hotelMarker = new window.google.maps.Marker({
      position: hotelPos,
      map: mapInstanceRef.current,
      title: "Your Location",
      label: {
        text: "YOU",
        color: "#ffffff",
        fontSize: "9px",
        fontWeight: "bold"
      },
      icon: {
        path: window.google.maps.SymbolPath.CIRCLE,
        scale: 14,
        fillColor: "#4f46e5",
        fillOpacity: 1,
        strokeColor: "#ffffff",
        strokeWeight: 2.5
      }
    });
    markersRef.current.push(hotelMarker);

    if (showResults) {
      recommendations.forEach(rec => {
        const coords = rec.coordinates || rec.facility?.coordinates || { lat: 41.8817, lng: -87.6278 };
        const recId = rec.id || rec.facility?.id;
        const isSelected = recId === selectedId;
        bounds.extend(coords);

        const marker = new window.google.maps.Marker({
          position: coords,
          map: mapInstanceRef.current,
          title: rec.name || rec.facility?.name || "Facility name unavailable",
          icon: isSelected 
            ? "http://maps.google.com/mapfiles/ms/icons/blue-dot.png" 
            : "http://maps.google.com/mapfiles/ms/icons/green-dot.png"
        });

        const ratingVal = rec.rating || 4.5;
        const walkTimeVal = rec.walk_minutes !== undefined ? rec.walk_minutes : rec.facility?.distance?.walking_time_minutes;
        const driveTimeVal = rec.drive_minutes !== undefined ? rec.drive_minutes : rec.facility?.distance?.transit_time_minutes;
        
        let priceLabel = "Price unknown";
        if (rec.effective_price === 0) {
          priceLabel = rec.access_type === 'membership_reciprocity' 
            ? "Free with YMCA Reciprocity" 
            : "Free";
        } else if (rec.effective_price !== null && rec.effective_price !== undefined) {
          priceLabel = `$${rec.effective_price} Day Pass`;
        }
        
        // Find Pool/Showers from amenities or badges
        const poolBadge = rec.amenities?.includes('pool') || rec.facility?.amenities?.includes('pool') || rec.facility?.emoji_badges?.some((b: string) => b.toLowerCase().includes('pool')) ? "🏊 Pool" : "";
        const showerBadge = rec.amenities?.includes('showers') || rec.facility?.amenities?.includes('showers') || rec.facility?.emoji_badges?.some((b: string) => b.toLowerCase().includes('shower')) ? "🚿 Showers" : "";
        const popupAmenities = [poolBadge, showerBadge].filter(Boolean).join(" • ");
        
        const popupHours = rec.opening_hours_summary || rec.facility_hours || (rec.facility?.hours?.close ? `Open until ${rec.facility?.hours?.close}` : "Hours unavailable");
        
        // Construct Google Maps URL following rules
        let mapsUrl = rec.google_maps_url;
        if (!mapsUrl || mapsUrl === "https://maps.google.com" || !mapsUrl.startsWith("http")) {
          if (rec.place_id && rec.place_id.startsWith("ChI")) {
            mapsUrl = `https://www.google.com/maps/search/?api=1&query=Google&query_place_id=${rec.place_id}`;
          } else {
            mapsUrl = `https://www.google.com/maps/search/?api=1&query=${coords.lat},${coords.lng}`;
          }
        }

        const nameVal = rec.name || rec.facility?.name || "Facility name unavailable";
        const contentString = `
          <div style="font-family: system-ui, -apple-system, sans-serif; color: #1e293b; padding: 6px; min-width: 180px; line-height: 1.45;">
            <div style="font-weight: 800; font-size: 0.85rem; margin-bottom: 2px; color: #0f172a;" class="map-popup-title">${nameVal}</div>
            <div style="font-size: 0.7rem; color: #64748b; margin-bottom: 4px; display: flex; gap: 4px; align-items: center; font-weight: 500;">
              <span>⭐ ${ratingVal}</span>
              <span>• 🚶 ${walkTimeVal !== null && walkTimeVal !== undefined ? `${walkTimeVal} min` : "Travel unavailable"}</span>
              <span>• 🚗 ${driveTimeVal !== null && driveTimeVal !== undefined ? `${driveTimeVal} min` : "Travel unavailable"}</span>
            </div>
            <div style="font-size: 0.72rem; font-weight: 700; color: #1e3a8a; margin-bottom: 4px;" class="map-popup-price">💰 ${priceLabel}</div>
            ${popupAmenities ? `<div style="font-size: 0.68rem; color: #475569; margin-bottom: 4px; font-weight: 500;">${popupAmenities}</div>` : ""}
            <div style="font-size: 0.68rem; color: #059669; font-weight: 600; margin-bottom: 4px;">${popupHours}</div>
            <div style="margin-top: 4px; border-top: 1px solid #e2e8f0; padding-top: 4px; display: flex; gap: 8px;">
              <a href="${rec.official_website_url || rec.website || 'https://maps.google.com'}" target="_blank" rel="noopener noreferrer" class="map-popup-website-link" style="color: #2563eb; text-decoration: none; font-weight: bold; font-size: 0.68rem; display: inline-block;">Facility website</a>
              <span style="color: #e2e8f0; font-size: 0.68rem;">•</span>
              <a href="${mapsUrl}" target="_blank" rel="noopener noreferrer" class="map-popup-link" style="color: #2563eb; text-decoration: none; font-weight: bold; font-size: 0.68rem; display: inline-block;">Open in Maps →</a>
            </div>
          </div>
        `;

        const showInfoWindow = () => {
          if (infoWindowRef.current && mapInstanceRef.current) {
            infoWindowRef.current.setContent(contentString);
            infoWindowRef.current.open(mapInstanceRef.current, marker);
          }
        };

        marker.addListener('mouseover', () => {
          showInfoWindow();
        });

        marker.addListener('click', () => {
          onSelectId(rec.facility.id);
          showInfoWindow();
        });

        if (isSelected) {
          setTimeout(() => {
            showInfoWindow();
          }, 150);
        }

        markersRef.current.push(marker);
      });

      if (recommendations.length > 0) {
        mapInstanceRef.current.fitBounds(bounds);
      }
    } else {
      mapInstanceRef.current.setCenter(hotelPos);
      mapInstanceRef.current.setZoom(14);
    }
  }, [recommendations, selectedId, showResults, resolvedLocation]);

  return <div ref={mapRef} style={{ width: '100%', height: '100%', borderRadius: '8px' }} />;
}

export default function App() {
  // Runtime config loaded from /config.json
  const [config, setConfig] = useState<{ apiBaseUrl: string; mapsApiKey: string }>({
    apiBaseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
    mapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ''
  });

  React.useEffect(() => {
    fetch('/config.json')
      .then(res => res.json())
      .then(data => {
        const apiBaseUrl = data.VITE_API_BASE_URL || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
        fetch(`${apiBaseUrl}/api/config`)
          .then(res => res.json())
          .then(configData => {
            setConfig({
              apiBaseUrl: apiBaseUrl,
              mapsApiKey: configData.mapsApiKey || ''
            });
          })
          .catch(err => {
            console.log("Failed to fetch maps API key from backend. Using fallback.", err);
            setConfig({
              apiBaseUrl: apiBaseUrl,
              mapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ''
            });
          });
      })
      .catch(err => {
        console.log("No runtime config.json found or failed to load. Using build env fallback.", err);
      });
  }, []);

  // Input fields
  const [location, setLocation] = useState("Downtown Chicago");
  const [budgetSelection, setBudgetSelection] = useState("20");
  const [hasYmca, setHasYmca] = useState(true);
  const [freeTextPreferences, setFreeTextPreferences] = useState("");
  const [selectedMemberships, setSelectedMemberships] = useState<string[]>(["YMCA"]);

  const toggleMembership = (name: string) => {
    setSelectedMemberships(prev => {
      const next = prev.includes(name) ? prev.filter(m => m !== name) : [...prev, name];
      if (name === "YMCA") {
        setHasYmca(next.includes("YMCA"));
      }
      return next;
    });
  };
  const [timeWindow, setTimeWindow] = useState("6:00 PM - 9:00 PM");
  
  // Required
  const [showersReq, setShowersReq] = useState(true);
  const [parkingReq, setParkingReq] = useState(false);

  // Preferred
  const [poolPref, setPoolPref] = useState(true);
  const [treadmillPref, setTreadmillPref] = useState(true);

  // Search execution status
  const [isSearching, setIsSearching] = useState(false);
  const [currentStageIndex, setCurrentStageIndex] = useState(-1);
  const [showResults, setShowResults] = useState(false);
  const [noOptionSatisfiesConstraints, setNoOptionSatisfiesConstraints] = useState(false);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [selectedRecId, setSelectedRecId] = useState<string>("");
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [dataWarning, setDataWarning] = useState<string | null>(null);
  const [resolvedLocation, setResolvedLocation] = useState<{
    display_name?: string;
    formatted_address?: string;
    place_id?: string;
    warning?: string | null;
  } | null>(null);

  // Premium Vertical Timeline Stages
  const timelineStages = [
    { 
      icon: "🧠", 
      title: "Understood your trip", 
      sentence: "Parsed location, time window, budget, membership, and preferences.",
      emoji: "🏃"
    },
    { 
      icon: "📍", 
      title: "Found nearby facilities", 
      sentence: "Located fitness options near Downtown Chicago.",
      emoji: "🏊"
    },
    { 
      icon: "🔑", 
      title: "Checked access", 
      sentence: "Compared day passes, YMCA reciprocity, and budget fit.",
      emoji: "💪"
    },
    { 
      icon: "🏊", 
      title: "Verified amenities", 
      sentence: "Checked pool, treadmill, showers, lockers, towels, and parking.",
      emoji: "🏃"
    },
    { 
      icon: "⭐", 
      title: "Ranked options", 
      sentence: "Compared distance, cost, rating, and amenity match.",
      emoji: "🏆"
    },
    { 
      icon: "🚗", 
      title: "Estimated travel", 
      sentence: "Calculated walking and driving times.",
      emoji: "🚴"
    },
    { 
      icon: "🛡️", 
      title: "Validated constraints", 
      sentence: "Applied the Policy & Validation Layer before showing results.",
      emoji: "🛡️"
    }
  ];

  const buildRecommendationSummary = (recs: Recommendation[], noSatisfies: boolean) => {
    if (recs.length === 0) return "";
    
    // Count how many actually passed validation
    const matchingRecs = recs.filter(r => r.eligibility_status === "Fits Your Criteria" || r.validation_status === "passed");
    const isFreeOnly = budgetSelection === "free";
    
    if (matchingRecs.length === 0 || noSatisfies) {
      if (isFreeOnly) {
        return "No verified free option found. Showing closest alternatives.";
      }
      return "No option satisfies all mandatory constraints. Showing closest alternatives.";
    }
    
    const topMatch = matchingRecs[0];
    const cost = topMatch.effective_price !== undefined ? topMatch.effective_price : topMatch.facility?.pricing?.cost;
    const costText = cost === 0 
      ? "is free" 
      : cost === null || cost === undefined
        ? "has unverified pricing"
        : `costs $${cost}`;
    const walkTime = topMatch.walk_minutes !== null && topMatch.walk_minutes !== undefined ? topMatch.walk_minutes : topMatch.facility?.distance?.walking_time_minutes;
    const nameVal = topMatch.name || topMatch.facility?.name || "Facility";

    return `I found ${matchingRecs.length} spaces matching your selections. ${nameVal} is your top match because it ${costText}, is only a ${walkTime}-minute walk away, and satisfies your requirements.`;
  };

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSearching(true);
    setCurrentStageIndex(0);
    setShowResults(false);
    setNoOptionSatisfiesConstraints(false);
    setIsDemoMode(false);
    setDataWarning(null);
    setResolvedLocation(null);

    // Resolve location
    try {
      const res = await fetch(`${config.apiBaseUrl}/resolve_location?address=${encodeURIComponent(location)}`);
      if (res.ok) {
        const data = await res.json();
        setResolvedLocation(data);
      } else {
        console.warn("Location resolution endpoint returned non-OK status");
      }
    } catch (err) {
      console.error("Location resolution request failed:", err);
    }

    const animateStages = async () => {
      for (let i = 0; i < timelineStages.length; i++) {
        setCurrentStageIndex(i);
        await new Promise(resolve => setTimeout(resolve, 300));
      }
    };

    const runBackendStream = async () => {
      try {
        let structuredRecs: any[] = [];
        const fullMarkdownText = await runConciergeStream({
          location,
          timeWindow,
          budgetSelection,
          hasYmca,
          showersReq,
          parkingReq,
          poolPref,
          treadmillPref,
          memberships: selectedMemberships,
          freeTextPreferences: freeTextPreferences
        }, (event) => {
          if (event.author === 'research_intelligence') {
            setCurrentStageIndex(prev => Math.min(Math.max(prev, 1), 3));
          } else if (event.author === 'ranking_itinerary') {
            setCurrentStageIndex(prev => Math.min(Math.max(prev, 4), 5));
          } else if (event.author === 'policy_validation') {
            setCurrentStageIndex(6);
          }
          if (event.type === 'result' && event.data) {
            const data = event.data;
            if (data.recommendations && data.recommendations.length > 0) {
              structuredRecs = data.recommendations;
            } else if (data.summary) {
              console.warn("Structured recommendations empty inside final_result data. Using fallback summary markdown parse.");
              const parsed = parseMarkdownToRecommendations(data.summary);
              if (parsed && parsed.length > 0) {
                structuredRecs = parsed;
              }
              setDataWarning("Structured JSON recommendations empty from backend. Using parsed markdown fallback.");
            }
          } else if (event.type === 'final_result') {
            if (event.recommendations && event.recommendations.length > 0) {
              structuredRecs = event.recommendations;
            }
          }
        }, () => {}, config.apiBaseUrl);

        const parsed = structuredRecs.length > 0 ? structuredRecs : parseMarkdownToRecommendations(fullMarkdownText);
        if (parsed && parsed.length > 0) {
          const uniqueRecs: Recommendation[] = [];
          const seenPlaceIds = new Set<string>();
          const seenNames = new Set<string>();
          
          parsed.forEach(r => {
            const pid = r.place_id || r.facility?.id;
            const normName = ((r.name || r.facility?.name || "") + "||" + (r.address || r.facility?.address || "")).toLowerCase().trim().replace(/[^a-z0-9|]/g, "");
            if (pid) {
              if (seenPlaceIds.has(pid)) return;
              seenPlaceIds.add(pid);
            }
            if (seenNames.has(normName)) return;
            seenNames.add(normName);
            uniqueRecs.push(r);
          });
          
          const cappedRecs = uniqueRecs.slice(0, 3);
          setRecommendations(cappedRecs);
          if (cappedRecs.length > 0) {
            setSelectedRecId(cappedRecs[0].id || cappedRecs[0].facility?.id || "");
          }
          const hasImpossible = cappedRecs.length > 0 && cappedRecs.every(r => r.eligibility_status === 'Rejected' || r.eligibility_status === 'Alternative');
          setNoOptionSatisfiesConstraints(hasImpossible);
          setIsDemoMode(false);
        } else {
          throw new Error("No recommendations parsed from streaming response.");
        }
      } catch (err: any) {
        console.error("Backend concierge unavailable, falling back to static demo:", err);
        setIsDemoMode(true);
        setDataWarning(err?.message || "Connection refused to backend concierge service.");
        await animateStages();
        if (budgetSelection === "free" || budgetSelection === "10" || !hasYmca) {
          setNoOptionSatisfiesConstraints(true);
          setRecommendations(USER_FACILITIES_IMPOSSIBLE);
          setSelectedRecId(USER_FACILITIES_IMPOSSIBLE[0].facility.id);
        } else {
          setRecommendations(USER_FACILITIES_ELIGIBLE);
          setSelectedRecId(USER_FACILITIES_ELIGIBLE[0].facility.id);
        }
      }
    };

    await Promise.all([
      runBackendStream(),
      new Promise(resolve => setTimeout(resolve, 1500))
    ]);

    setIsSearching(false);
    setShowResults(true);
  };

  const selectedRec = recommendations.find(r => r.facility.id === selectedRecId);

  const getPhotoUrl = (rec: Recommendation) => {
    if (rec.photo_url) return rec.photo_url;
    const id = rec.facility?.id || rec.id;
    if (id === 'ymca_chicago') return 'https://images.unsplash.com/photo-1571902943202-507ec2618e8f?auto=format&fit=crop&w=400&q=80';
    if (id === 'ffc_union') return 'https://images.unsplash.com/photo-1540497077202-7c8a3999166f?auto=format&fit=crop&w=400&q=80';
    return 'https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=crop&w=400&q=80';
  };

  const getRankBadgeClass = (rank: number) => {
    if (rank === 1) return "quality-badge best";
    if (rank === 2) return "quality-badge alternative";
    return "quality-badge value";
  };

  const getRankLabel = (rank: number) => {
    if (rank === 1) return "🏆 Best Match";
    if (rank === 2) return "⭐ Premium Club";
    return "💰 Lowest Paid Pass";
  };

  const getAccessText = (rec: any) => {
    const status = rec.access_status || rec.facility?.access_status;
    const name = (rec.name || rec.facility?.name || "").toLowerCase();
    
    if (status === "verified_member_access") {
      if (name.includes("ymca")) return "Access: Free with YMCA";
      if (name.includes("planet fitness")) return "Access: Free with Planet Fitness";
      if (name.includes("life time") || name.includes("lifetime")) return "Access: Free with Life Time";
      if (name.includes("equinox")) return "Access: Free with Equinox";
      if (name.includes("ffc")) return "Access: Free with FFC";
      if (name.includes("la fitness")) return "Access: Free with LA Fitness";
      if (name.includes("hotel gym")) return "Access: Free with Hotel Gym";
      return "Access: Free with Membership";
    } else if (status === "membership_required") {
      if (name.includes("planet fitness")) return "Access: Planet Fitness membership required";
      if (name.includes("life time") || name.includes("lifetime")) return "Access: Life Time membership required";
      if (name.includes("equinox")) return "Access: Equinox membership required";
      return "Access: Membership required";
    } else if (status === "verified_day_pass") {
      return "Access: Verified day pass";
    } else if (status === "free_public_access") {
      return "Access: Free public access";
    } else if (status === "rejected") {
      return "Access: Rejected (Ineligible)";
    } else {
      return "Access: Day pass unknown";
    }
  };

  return (
    <div className="app-container">
      
      {/* 1. TOP NAV */}
      <header className="top-nav">
        <div className="brand-section">
          <div className="brand-logo">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <div className="brand-name">TravelWell AI</div>
            <div className="brand-tagline">Find Your Perfect Workout. Anywhere. Anytime.</div>
          </div>
        </div>
      </header>

      {/* 2. HERO GREETING */}
      <section className="hero">
        <h1 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#0f172a', margin: '0 0 4px 0' }}>
          TravelWell AI
        </h1>
        <h2 style={{ fontSize: '0.95rem', fontWeight: 600, color: '#2563eb', margin: '0 0 6px 0' }}>
          Find Your Perfect Workout. Anywhere. Anytime.
        </h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '8px' }}>
          <span style={{ background: '#eff6ff', color: '#1e40af', fontSize: '0.725rem', fontWeight: 700, padding: '3px 8px', borderRadius: '4px' }}>
            ⚡ Powered by Explainable Multi-Agent AI
          </span>
          <span style={{ background: '#ecfdf5', color: '#065f46', fontSize: '0.725rem', fontWeight: 700, padding: '3px 8px', borderRadius: '4px' }}>
            🛡️ Every recommendation explained
          </span>
        </div>
        <p style={{ fontSize: '0.8rem', color: '#64748b', margin: '4px 0 0 0' }}>Compare fitness matches that fit your active memberships, travel schedule, and facility checklists.</p>
      </section>

      {/* 3. DASHBOARD GRID (3 Columns: Form, Map, Vertical Workflow) */}
      <ErrorBoundary>
        <div className="dashboard-grid">
        
        {/* Left Card: Trip Planner Form */}
        <div className="white-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '14px' }}>
            <Sparkles className="w-4 h-4 text-blue-600" />
            <h2 style={{ fontSize: '0.9rem', fontWeight: 700, margin: 0 }}>Configure Wellness Search</h2>
          </div>

          <form onSubmit={handleSearchSubmit}>
            <div className="form-group">
              <label>Location coordinates</label>
              <input 
                type="text" 
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="form-input" 
                placeholder="Hotel, coordinates, or city..."
              />
              {resolvedLocation && (
                <div style={{ marginTop: '6px', fontSize: '0.75rem', color: '#475569', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                  <div>
                    📍 <strong>Searching near:</strong> {resolvedLocation.formatted_address || resolvedLocation.display_name}
                  </div>
                  {resolvedLocation.warning && (
                    <div style={{ color: '#d97706', fontWeight: 600 }}>
                      ⚠️ {resolvedLocation.warning}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="form-group">
              <label>Available travel window</label>
              <input 
                type="text" 
                value={timeWindow}
                onChange={(e) => setTimeWindow(e.target.value)}
                className="form-input" 
                placeholder="e.g. 6:00 PM - 9:00 PM"
              />
            </div>

            {/* Clickable Budget Chips */}
            <div className="form-group">
              <label>Pass Budget Cap</label>
              <div className="budget-chips-container">
                <button
                  type="button"
                  onClick={() => setBudgetSelection("none")}
                  className={`budget-chip ${budgetSelection === "none" ? 'active' : ''}`}
                >
                  No limit
                </button>
                <button
                  type="button"
                  onClick={() => setBudgetSelection("free")}
                  className={`budget-chip ${budgetSelection === "free" ? 'active' : ''}`}
                >
                  Free only
                </button>
                <button
                  type="button"
                  onClick={() => setBudgetSelection("10")}
                  className={`budget-chip ${budgetSelection === "10" ? 'active' : ''}`}
                >
                  Under $10
                </button>
                <button
                  type="button"
                  onClick={() => setBudgetSelection("20")}
                  className={`budget-chip ${budgetSelection === "20" ? 'active' : ''}`}
                >
                  Under $20
                </button>
                <button
                  type="button"
                  onClick={() => setBudgetSelection("30")}
                  className={`budget-chip ${budgetSelection === "30" ? 'active' : ''}`}
                >
                  Under $30
                </button>
              </div>
            </div>

            <div className="form-group">
              <label>YMCA RECIPROCITY</label>
              <div className="pills-container">
                <button
                  type="button"
                  onClick={() => {
                    setHasYmca(true);
                    if (!selectedMemberships.includes("YMCA")) {
                      setSelectedMemberships(prev => [...prev, "YMCA"]);
                    }
                  }}
                  className={`toggle-btn ${hasYmca ? 'active' : ''}`}
                >
                  {hasYmca && <Check className="w-3.5 h-3.5" />}
                  Active Member
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setHasYmca(false);
                    setSelectedMemberships(prev => prev.filter(m => m !== "YMCA"));
                  }}
                  className={`toggle-btn ${!hasYmca ? 'active' : ''}`}
                >
                  {!hasYmca && <Check className="w-3.5 h-3.5" />}
                  No YMCA
                </button>
              </div>
            </div>

            <div className="form-group">
              <label>ACTIVE MEMBERSHIPS</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {["YMCA", "Planet Fitness", "Life Time", "FFC", "LA Fitness", "Equinox", "Hotel Gym", "Other"].map((m) => {
                  const isActive = selectedMemberships.includes(m);
                  return (
                    <button
                      key={m}
                      type="button"
                      onClick={() => toggleMembership(m)}
                      className={`toggle-btn ${isActive ? 'active' : ''}`}
                      style={{ padding: '4px 10px', fontSize: '0.75rem', borderRadius: '99px' }}
                    >
                      {isActive && <Check className="w-3.5 h-3.5" />}
                      {m}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="form-group">
              <label>ADDITIONAL PREFERENCES</label>
              <textarea
                value={freeTextPreferences}
                onChange={(e) => setFreeTextPreferences(e.target.value)}
                placeholder="Tell TravelWell anything else: Planet Fitness Black Card, hotel gym access, lap swim only, women-only gym, sauna, open after 8 PM..."
                style={{
                  width: '100%',
                  minHeight: '60px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  padding: '8px',
                  fontSize: '0.8rem',
                  fontFamily: 'inherit',
                  resize: 'vertical'
                }}
              />
            </div>

            {/* Required Preferences */}
            <div className="form-group">
              <label>Required Constraints</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => setShowersReq(!showersReq)}
                  className={`toggle-btn ${showersReq ? 'active' : ''}`}
                >
                  {showersReq && <Check className="w-3.5 h-3.5" />}
                  🚿 Showers
                </button>
                <button
                  type="button"
                  onClick={() => setParkingReq(!parkingReq)}
                  className={`toggle-btn ${parkingReq ? 'active' : ''}`}
                >
                  {parkingReq && <Check className="w-3.5 h-3.5" />}
                  🅿️ Free parking
                </button>
              </div>
            </div>

            {/* Preferred Preferences */}
            <div className="form-group" style={{ marginBottom: '10px' }}>
              <label>Preferred Amenities</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                <button
                  type="button"
                  onClick={() => setPoolPref(!poolPref)}
                  className={`toggle-btn ${poolPref ? 'active' : ''}`}
                >
                  {poolPref && <Check className="w-3.5 h-3.5" />}
                  🏊 Indoor pool
                </button>
                <button
                  type="button"
                  onClick={() => setTreadmillPref(!treadmillPref)}
                  className={`toggle-btn ${treadmillPref ? 'active' : ''}`}
                >
                  {treadmillPref && <Check className="w-3.5 h-3.5" />}
                  🏃 Treadmill
                </button>
              </div>
            </div>

            {/* Summary Box */}
            <div className="summary-box" style={{ marginBottom: '10px' }}>
              <strong>Selections Summary:</strong><br />
              📍 {location} | Budget: {budgetSelection === "none" ? "No limit" : budgetSelection === "free" ? "Free" : `Under $${budgetSelection}`} | YMCA: {hasYmca ? "Yes" : "No"} | 
              Constraints: {[showersReq ? "Showers" : null, parkingReq ? "Free Parking" : null, poolPref ? "Pool" : null, treadmillPref ? "Treadmill" : null].filter(Boolean).join(", ") || "None"}
            </div>

            <button type="submit" className="btn-submit">
              {isSearching ? 'Orchestrating...' : '🔍 Find My Workout'}
            </button>
          </form>
        </div>

        {/* Middle Card: Fake Map Panel */}
        <div className="white-card" style={{ padding: '12px', position: 'relative' }}>
          <div className="map-visual">
            {!showResults && !isSearching ? (
              <div style={{
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
                padding: '24px',
                textAlign: 'center',
                background: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)',
                borderRadius: '8px',
                border: '2px dashed #cbd5e1'
              }}>
                <div style={{
                  background: '#dbeafe',
                  color: '#2563eb',
                  padding: '12px',
                  borderRadius: '999px',
                  marginBottom: '16px'
                }}>
                  <Compass className="w-8 h-8" />
                </div>
                <h3 style={{ fontSize: '1rem', fontWeight: 800, color: '#0f172a', marginBottom: '8px' }}>
                  Ready to Plan Your Workout?
                </h3>
                <p style={{ fontSize: '0.8rem', color: '#475569', maxWidth: '280px', lineHeight: '1.4', marginBottom: '20px' }}>
                  Tell TravelWell where you’ll be, and I’ll find your best workout options nearby.
                </p>
                <div style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '8px',
                  justifyContent: 'center',
                  maxWidth: '320px'
                }}>
                  <span style={{ background: '#ffffff', color: '#334155', fontSize: '0.7rem', fontWeight: 600, padding: '4px 10px', borderRadius: '99px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>📍 Location</span>
                  <span style={{ background: '#ffffff', color: '#334155', fontSize: '0.7rem', fontWeight: 600, padding: '4px 10px', borderRadius: '99px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>🕕 Time window</span>
                  <span style={{ background: '#ffffff', color: '#334155', fontSize: '0.7rem', fontWeight: 600, padding: '4px 10px', borderRadius: '99px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>💳 Budget</span>
                  <span style={{ background: '#ffffff', color: '#334155', fontSize: '0.7rem', fontWeight: 600, padding: '4px 10px', borderRadius: '99px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>🏋️ Workout preference</span>
                  <span style={{ background: '#ffffff', color: '#334155', fontSize: '0.7rem', fontWeight: 600, padding: '4px 10px', borderRadius: '99px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>🔑 Memberships</span>
                  <span style={{ background: '#ffffff', color: '#334155', fontSize: '0.7rem', fontWeight: 600, padding: '4px 10px', borderRadius: '99px', border: '1px solid #e2e8f0', boxShadow: '0 1px 2px rgba(0,0,0,0.05)' }}>🛡️ Required amenities</span>
                </div>
              </div>
            ) : config.mapsApiKey ? (
              <GoogleMapComponent 
                apiKey={config.mapsApiKey} 
                recommendations={recommendations} 
                selectedId={selectedRecId} 
                onSelectId={setSelectedRecId} 
                showResults={showResults} 
                resolvedLocation={resolvedLocation}
              />
            ) : (
              <>
                <svg className="w-full h-full" style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }} viewBox="0 0 800 450" preserveAspectRatio="none">
                  <defs>
                    <pattern id="grid-dots" width="30" height="30" patternUnits="userSpaceOnUse">
                      <circle cx="1.5" cy="1.5" r="1.2" fill="rgba(37, 99, 235, 0.04)" />
                    </pattern>
                  </defs>
                  <rect width="100%" height="100%" fill="url(#grid-dots)" />

                  {/* Street grids with text labels */}
                  <path d="M 120 0 L 120 450" stroke="#e2e8f0" strokeWidth="5" />
                  <path d="M 330 0 L 330 450" stroke="#e2e8f0" strokeWidth="5" />
                  <path d="M 640 0 L 640 450" stroke="#e2e8f0" strokeWidth="5" />
                  <path d="M 0 160 L 800 160" stroke="#e2e8f0" strokeWidth="5" />
                  <path d="M 0 320 L 800 320" stroke="#e2e8f0" strokeWidth="5" />

                  <text x="128" y="40" fill="#94a3b8" fontSize="9" fontWeight="bold">Halsted St</text>
                  <text x="338" y="40" fill="#94a3b8" fontSize="9" fontWeight="bold">Jackson Blvd</text>
                  <text x="648" y="40" fill="#94a3b8" fontSize="9" fontWeight="bold">Michigan Ave</text>
                  <text x="20" y="152" fill="#94a3b8" fontSize="9" fontWeight="bold">Wacker Dr</text>
                  <text x="20" y="312" fill="#94a3b8" fontSize="9" fontWeight="bold">State St</text>

                  {/* Walking Radius Circles from starting hotel */}
                  <circle cx="450" cy="220" r="120" fill="none" stroke="rgba(37, 99, 235, 0.05)" strokeWidth="1" strokeDasharray="4,4" />
                  <text x="450" y="335" fill="#94a3b8" fontSize="8" textAnchor="middle">10 min walk radius</text>
                  <circle cx="450" cy="220" r="230" fill="none" stroke="rgba(37, 99, 235, 0.03)" strokeWidth="1" strokeDasharray="4,4" />
                  <text x="450" y="442" fill="#94a3b8" fontSize="8" textAnchor="middle">20 min walk radius</text>

                  {/* Travel routes to gyms: Blue for selected, Gray for alternatives */}
                  {showResults && recommendations.map((rec) => {
                    const isSelected = rec.facility.id === selectedRecId;
                    const pathD = rec.facility.id === 'ymca_chicago' 
                      ? "M 450 220 L 640 220 L 640 280" 
                      : rec.facility.id === 'ffc_union'
                        ? "M 450 220 L 330 220 L 330 300"
                        : "M 450 220 L 120 220 L 120 180";
                    return (
                      <path 
                        key={rec.facility.id}
                        d={pathD} 
                        fill="none" 
                        stroke={isSelected ? "#2563eb" : "#cbd5e1"} 
                        strokeWidth={isSelected ? "4.5" : "2.5"} 
                        strokeDasharray={isSelected ? "none" : "5,5"}
                        opacity={isSelected ? "1" : "0.6"}
                      />
                    );
                  })}

                  {/* Starting hotel pin */}
                  <circle cx="450" cy="220" r="7" fill="#ef4444" stroke="#ffffff" strokeWidth="2.5" />
                  <text x="450" y="202" fill="#1e293b" fontSize="9" fontWeight="bold" textAnchor="middle">📍 Your Hotel</text>
                </svg>

                {/* Pins directly with names attached */}
                {showResults && recommendations.map((rec) => {
                  const isSelected = rec.facility.id === selectedRecId;
                  const position = rec.facility.id === 'ymca_chicago' 
                    ? { left: '640px', top: '280px' } 
                    : rec.facility.id === 'ffc_union'
                      ? { left: '330px', top: '300px' }
                      : { left: '120px', top: '180px' };

                  const pinLabel = rec.rank === 1 ? "🏆 YMCA" : rec.rank === 2 ? "② FFC" : "③ Planet Fitness";

                  return (
                    <div 
                      key={rec.facility.id}
                      onClick={() => setSelectedRecId(rec.facility.id)}
                      style={{
                        position: 'absolute',
                        left: position.left,
                        top: position.top,
                        transform: 'translate(-50%, -100%)',
                        cursor: 'pointer',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        zIndex: isSelected ? 12 : 5
                      }}
                    >
                      {/* Small Walk/Drive travel bubble */}
                      <div style={{
                        background: isSelected ? '#1e3a8a' : '#475569',
                        color: '#ffffff',
                        fontSize: '0.58rem',
                        fontWeight: 700,
                        padding: '2px 6px',
                        borderRadius: '4px',
                        marginBottom: '2px',
                        whiteSpace: 'nowrap'
                      }}>
                        🚶{rec.facility?.distance?.walking_time_minutes || 0}m / 🚗{rec.facility?.distance?.transit_time_minutes || 0}m
                      </div>

                      <div style={{
                        background: isSelected ? '#2563eb' : '#ffffff',
                        color: isSelected ? '#ffffff' : '#1e293b',
                        fontSize: '0.68rem',
                        fontWeight: 800,
                        padding: '3px 8px',
                        borderRadius: '4px',
                        border: isSelected ? '1px solid #2563eb' : '1px solid #cbd5e1',
                        boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                        whiteSpace: 'nowrap'
                      }}>
                        {pinLabel}
                      </div>
                    </div>
                  );
                })}

                {/* Map Legend */}
                <div className="map-legend">
                  <div style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                    <span style={{ width: '8px', height: '8px', borderRadius: '99px', background: '#ef4444', display: 'inline-block' }} />
                    <span>Hotel</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                    <span style={{ width: '12px', height: '2px', background: '#2563eb', display: 'inline-block' }} />
                    <span>Selected Route</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '3px' }}>
                    <span style={{ width: '12px', height: '0px', borderBottom: '2px dashed #cbd5e1', display: 'inline-block' }} />
                    <span>Alternative</span>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Right Card: AI Concierge Premium Vertical Timeline */}
        <div className="white-card" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div>
            <h2 style={{ fontSize: '0.9rem', fontWeight: 800, margin: 0, color: '#0f172a' }}>AI Concierge</h2>
            <div style={{ fontSize: '0.7rem', color: '#64748b', fontWeight: 500 }}>How I found your recommendation</div>
          </div>

          <div className="timeline-container-v" style={{ marginTop: '8px' }}>
            <div className="timeline-line-v" />

            {timelineStages.map((stage, idx) => {
              const isCurrent = idx === currentStageIndex;
              const isPassed = idx < currentStageIndex || showResults;
              
              let statusClass = 'waiting';
              if (isPassed) {
                statusClass = 'complete';
              } else if (isCurrent) {
                statusClass = 'active';
              }

              return (
                <div key={idx} className={`timeline-item-v ${statusClass}`}>
                  {/* Left node timeline circle/dot */}
                  <div className={`timeline-dot-v ${statusClass}`} />

                  {/* Header Row */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontWeight: 700, fontSize: '0.725rem', color: isPassed ? '#1e293b' : '#64748b' }}>
                    <span>{stage.icon}</span>
                    <span>{stage.title}</span>
                    {isPassed && <span style={{ color: '#10b981', fontSize: '0.65rem', marginLeft: '4px' }}>✓</span>}
                    {isCurrent && (
                      <span className="playful-runner">
                        {stage.emoji}
                      </span>
                    )}
                  </div>

                  {/* Status subtext sentence */}
                  <div style={{ fontSize: '0.625rem', color: isPassed ? '#475569' : '#94a3b8', lineHeight: '1.25' }}>
                    {stage.sentence}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

      </div>
      </ErrorBoundary>

      {/* AI Concierge Summary Banner */}
      {showResults && recommendations.length > 0 && (
        <div className="concierge-summary-card">
          <strong>💡 AI Recommendation Details:</strong> {buildRecommendationSummary(recommendations, noOptionSatisfiesConstraints)}
        </div>
      )}

      {/* 5. RECOMMENDATIONS GRID */}
      {!showResults && !isSearching && (
        <div className="white-card" style={{ textAlign: 'center', padding: '40px 20px', color: '#64748b', marginBottom: '20px' }}>
          <Compass className="w-8 h-8 text-blue-500" style={{ margin: '0 auto 12px auto' }} />
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#1e293b', marginBottom: '4px' }}>No Workout Plan Loaded</h3>
          <p style={{ fontSize: '0.8rem', margin: 0 }}>
            Tell TravelWell where you'll be and what kind of workout you need.
          </p>
        </div>
      )}

      {showResults && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {isDemoMode ? (
            <div className="white-card" style={{ background: '#fef3c7', borderColor: '#fde68a', color: '#92400e', padding: '10px 16px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', width: '100%' }}>
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                <span style={{ fontWeight: 700, fontSize: '0.85rem' }}>Using demo data because the live concierge service is unavailable.</span>
                <span style={{ marginLeft: 'auto', background: '#d97706', color: '#fff', fontSize: '0.625rem', fontWeight: 800, padding: '2px 6px', borderRadius: '4px', textTransform: 'uppercase' }}>Demo Fallback</span>
              </div>
              {dataWarning && (
                <div style={{ fontSize: '0.75rem', color: '#b45309', borderTop: '1px dashed #fcd34d', paddingTop: '4px', marginTop: '2px' }}>
                  <strong>Live failure reason:</strong> {dataWarning}
                </div>
              )}
            </div>
          ) : (
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '4px' }}>
              <span style={{ background: '#10b981', color: '#fff', fontSize: '0.625rem', fontWeight: 800, padding: '3px 8px', borderRadius: '4px', textTransform: 'uppercase', display: 'flex', alignItems: 'center', gap: '4px' }}>✨ Live Google Data</span>
            </div>
          )}

          {noOptionSatisfiesConstraints && (
            <div className="white-card" style={{ background: '#fef2f2', borderColor: '#fee2e2', color: '#b91c1c', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <AlertTriangle className="w-4 h-4 text-red-500" />
              <span style={{ fontWeight: 700, fontSize: '0.85rem' }}>No option satisfies all mandatory constraints. Showing closest alternatives.</span>
            </div>
          )}

          <div className="recommendations-grid">
            {recommendations.map((rec) => {
              const isSelected = rec.facility.id === selectedRecId;
              const badgeSymbol = getRankLabel(rec.rank);
              const badgeClass = getRankBadgeClass(rec.rank);

              return (
                <div
                  key={rec.facility.id}
                  onClick={() => setSelectedRecId(rec.facility.id)}
                  className={`rec-card ${isSelected ? 'selected' : ''}`}
                >
                  {/* Photo Cover Area with bottom gradient overlay */}
                  <div className="photo-area" style={{ backgroundImage: `url(${getPhotoUrl(rec)})` }}>
                    <div className="photo-gradient" />
                  </div>

                  <div className="rec-card-body">
                    {/* Badge Column (badge on top, explanation below it) */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', alignItems: 'flex-start' }}>
                      <span className={badgeClass}>{badgeSymbol}</span>
                      <span style={{ fontSize: '0.65rem', color: '#64748b', fontStyle: 'italic', paddingLeft: '4px' }}>
                        {rec.badge_subtitle}
                      </span>
                    </div>

                    {/* Facility Name Block */}
                    <div>
                      <h3 className="card-title" style={{ fontSize: '0.95rem', fontWeight: 800, margin: '4px 0', color: '#0f172a' }}>
                        {rec.name}
                      </h3>
                      <div className="card-address" style={{ fontSize: '0.75rem', color: '#64748b' }}>
                        {rec.address}
                      </div>
                      <div style={{ fontSize: '0.75rem', fontWeight: 700, margin: '4px 0', color: rec.access_status === "verified_member_access" || rec.access_status === "free_public_access" ? "#10b981" : rec.access_status === "membership_required" || rec.access_status === "rejected" ? "#ef4444" : "#f59e0b" }}>
                        🔑 {getAccessText(rec)}
                      </div>
                    </div>

                    {/* Metrics Row (Free is highlighted) */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '4px', padding: '6px 0', borderTop: '1px solid #f1f5f9', borderBottom: '1px solid #f1f5f9' }}>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: '0.58rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase' }}>Rating</div>
                        <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#334155' }}>⭐ {rec.rating}</div>
                      </div>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: '0.58rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase' }}>Travel</div>
                        <div style={{ fontSize: '0.75rem', fontWeight: 700, color: '#334155' }}>🚶 {rec.walk_minutes}m</div>
                      </div>
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: '0.58rem', fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase' }}>Day Pass</div>
                        <div className="card-price" style={{ fontSize: '0.75rem', fontWeight: 800, color: rec.effective_price === 0 ? '#10b981' : '#334155' }}>
                          {rec.effective_price === 0 ? "FREE Reciprocity" : (rec.effective_price === null || rec.effective_price === undefined) ? "Pricing Unknown" : `$${rec.effective_price}`}
                        </div>
                      </div>
                    </div>

                    {/* Amenities Row */}
                    <div>
                      <div className="amenity-chips">
                        {rec.facility.emoji_badges.map((badge, i) => (
                          <span key={i} className="amenity-chip-item">{badge}</span>
                        ))}
                      </div>
                    </div>

                    {/* Operational Status Row */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.7rem', fontWeight: 700, color: '#2563eb' }}>
                      <span>
                        {rec.is_open_now ? "🟢 Open now" : "🔴 Closed"}
                        {rec.opening_hours_summary ? ` • ${rec.opening_hours_summary}` : ""}
                      </span>
                    </div>

                    {/* Card Concierge summary line at the bottom */}
                    <div style={{ borderTop: '1px dashed #e2e8f0', paddingTop: '6px', fontSize: '0.68rem', color: '#475569', fontWeight: 500 }}>
                      {rec.card_summary}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 6. EXPANDED COMPACT TWO-COLUMN SELECTED FACILITY DETAIL VIEW */}
      {showResults && selectedRec && (
        <ErrorBoundary>
          <div className="white-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px', paddingBottom: '8px', borderBottom: '1px solid #e2e8f0' }}>
            <span style={{ fontSize: '1.2rem' }}>{selectedRec.rank === 1 ? "🏆" : selectedRec.rank === 2 ? "🥈" : "💰"}</span>
            <h2 style={{ fontSize: '1.05rem', fontWeight: 800, margin: 0, color: '#0f172a' }}>
              Selected Facility: {selectedRec.name}
            </h2>
          </div>

          <div className="detail-columns">
            
            {/* Left: Policy Check & rationale */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
                  <Check className="w-4 h-4 text-emerald-600" />
                  <h3 style={{ fontSize: '0.8rem', fontWeight: 800, margin: 0 }}>Policy Check</h3>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                  <div className={`satisfied-chip ${
                    selectedRec.amenity_states?.pool === 'verified' ? 'yes' : 
                    selectedRec.amenity_states?.pool === 'unavailable' ? 'no' : 'unknown'
                  }`}>
                    <span>{
                      selectedRec.amenity_states?.pool === 'verified' ? '✅' : 
                      selectedRec.amenity_states?.pool === 'unavailable' ? '❌' : '❓'
                    }</span>
                    <span>Indoor pool {selectedRec.amenity_states?.pool === 'unknown' && ' (not verified)'}</span>
                  </div>
                  <div className={`satisfied-chip ${
                    selectedRec.amenity_states?.treadmill === 'verified' ? 'yes' : 
                    selectedRec.amenity_states?.treadmill === 'unavailable' ? 'no' : 'unknown'
                  }`}>
                    <span>{
                      selectedRec.amenity_states?.treadmill === 'verified' ? '✅' : 
                      selectedRec.amenity_states?.treadmill === 'unavailable' ? '❌' : '❓'
                    }</span>
                    <span>Treadmill {selectedRec.amenity_states?.treadmill === 'unknown' && ' (not verified)'}</span>
                  </div>
                  <div className={`satisfied-chip ${
                    selectedRec.amenity_states?.showers === 'verified' ? 'yes' : 
                    selectedRec.amenity_states?.showers === 'unavailable' ? 'no' : 'unknown'
                  }`}>
                    <span>{
                      selectedRec.amenity_states?.showers === 'verified' ? '✅' : 
                      selectedRec.amenity_states?.showers === 'unavailable' ? '❌' : '❓'
                    }</span>
                    <span>Showers {selectedRec.amenity_states?.showers === 'unknown' && ' (not verified)'}</span>
                  </div>
                  <div className={`satisfied-chip ${
                    selectedRec.amenity_states?.parking === 'verified' ? 'yes' : 
                    selectedRec.amenity_states?.parking === 'unavailable' ? 'no' : 'unknown'
                  }`}>
                    <span>{
                      selectedRec.amenity_states?.parking === 'verified' ? '✅' : 
                      selectedRec.amenity_states?.parking === 'unavailable' ? '❌' : '❓'
                    }</span>
                    <span>Free parking {selectedRec.amenity_states?.parking === 'unknown' && ' (not verified)'}</span>
                  </div>
                </div>
              </div>

              <div style={{ fontSize: '0.78rem', color: '#475569', lineHeight: '1.4' }}>
                <strong>Concierge Details:</strong> {selectedRec.recommendation_reason}
              </div>

              {/* Contact Information block */}
              <div>
                <strong style={{ fontSize: '0.78rem', color: '#0f172a', display: 'block', marginBottom: '6px' }}>Contact Information</strong>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  <div className="info-btn" style={{ cursor: 'default' }}>
                    <MapPin className="w-3.5 h-3.5 text-slate-500" />
                    <span className="detail-address">{selectedRec.address || "Address unavailable"}</span>
                  </div>
                  <a href={`tel:${selectedRec.phone_number || selectedRec.facility?.phone}`} className="info-btn">
                    <Phone className="w-3.5 h-3.5" />
                    <span>Call ({selectedRec.phone_number || selectedRec.facility?.phone || "Unknown Phone"})</span>
                  </a>
                  <a href={selectedRec.official_website_url || selectedRec.website || selectedRec.facility?.website} target="_blank" rel="noreferrer" className="info-btn detail-website-link">
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>Facility website</span>
                  </a>
                  {(() => {
                    let mapsUrl = selectedRec.google_maps_url;
                    if (!mapsUrl || mapsUrl === "https://maps.google.com" || !mapsUrl.startsWith("http")) {
                      const coords = selectedRec.coordinates || selectedRec.facility?.coordinates || { lat: 41.8817, lng: -87.6278 };
                      if (selectedRec.place_id && selectedRec.place_id.startsWith("ChI")) {
                        mapsUrl = `https://www.google.com/maps/search/?api=1&query=Google&query_place_id=${selectedRec.place_id}`;
                      } else {
                        mapsUrl = `https://www.google.com/maps/search/?api=1&query=${coords.lat},${coords.lng}`;
                      }
                    }
                    return (
                      <a href={mapsUrl} target="_blank" rel="noreferrer" className="info-btn detail-open-maps-link">
                        <Compass className="w-3.5 h-3.5 text-emerald-600" />
                        <span>Open in Maps</span>
                      </a>
                    );
                  })()}
                </div>
              </div>
            </div>

            {/* Right: Visit Information */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
                <Calendar className="w-4 h-4 text-blue-600" />
                <h3 style={{ fontSize: '0.8rem', fontWeight: 800, margin: 0 }}>Visit Information</h3>
              </div>

              <div className="schedule-timeline" style={{ fontSize: '0.78rem', color: '#475569', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Clock className="w-4 h-4 text-blue-500" />
                  <div>
                    <strong>Hours Status:</strong> {selectedRec.is_open_now ? "Open now" : "Closed"} {selectedRec.opening_hours_summary ? `• ${selectedRec.opening_hours_summary}` : ""}
                  </div>
                </div>

                {(selectedRec.pool_hours || selectedRec.facility?.hours?.pool_hours) && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '0.9rem' }}>🏊</span>
                    <div>
                      <strong>Pool Schedule:</strong> {selectedRec.pool_hours || selectedRec.facility.hours.pool_hours}
                    </div>
                  </div>
                )}

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '0.9rem' }}>⏱️</span>
                  <div>
                    <strong>Estimated Visit Duration:</strong> 90 - 120 minutes recommended.
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '0.9rem' }}>🚗</span>
                  <div>
                    <strong>Travel Times:</strong> {selectedRec.facility.distance.walking_time_minutes} min walk / {selectedRec.facility.distance.transit_time_minutes} min drive ({selectedRec.facility.distance.description} walk).
                  </div>
                </div>

                {selectedRec.facility.crowd_warning && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: '#fffbeb', border: '1px solid #fef3c7', padding: '6px 10px', borderRadius: '8px', color: '#b45309', fontWeight: 600 }}>
                    <span>⚠️</span>
                    <div>
                      <strong>Crowd warning:</strong> {selectedRec.facility.crowd_warning}
                    </div>
                  </div>
                )}
              </div>
            </div>

          </div>
        </div>
        </ErrorBoundary>
      )}

    </div>
  );
}
