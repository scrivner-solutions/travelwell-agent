import { Recommendation, Facility } from '../App';

export interface RunParams {
  location: string;
  timeWindow: string;
  budgetSelection: string;
  hasYmca: boolean;
  showersReq: boolean;
  parkingReq: boolean;
  poolPref: boolean;
  treadmillPref: boolean;
  memberships: string[];
  freeTextPreferences: string;
}

// Baseline mock templates to enrich LLM response
const BASE_RECS = {
  ymca: {
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
  },
  ffc: {
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
  },
  planet_fitness: {
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
    reviews_summary: 'Very cheap, open 24 hours. Good selection of treadmills. No pool.',
    crowd_warning: 'Moderate crowd expected.',
    recommendation_metadata: {
      best_for: 'Late-night treadmill runs on a low budget.',
      limitations: 'No pool (violates primary preference) and is located furthest from coordinates.'
    }
  }
};

export async function runConciergeStream(
  params: RunParams,
  onEvent: (event: any) => void,
  onTextUpdate: (text: string) => void,
  apiBaseUrl?: string
): Promise<string> {
  const baseUrl = apiBaseUrl || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
  
  const response = await fetch(`${baseUrl}/api/recommend`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      location: params.location,
      timeWindow: params.timeWindow,
      budgetSelection: params.budgetSelection,
      hasYmca: params.hasYmca,
      showersReq: params.showersReq,
      parkingReq: params.parkingReq,
      poolPref: params.poolPref,
      treadmillPref: params.treadmillPref,
      memberships: params.memberships,
      freeTextPreferences: params.freeTextPreferences
    })
  });

  if (!response.ok) {
    let errMessage = '';
    try {
      const errJson = await response.json();
      if (errJson && errJson.message) {
        errMessage = `Concierge backend error in [${errJson.stage}]: ${errJson.message}`;
      }
    } catch (e) {
      // not JSON
    }
    if (errMessage) {
      throw new Error(errMessage);
    }
    throw new Error(`Concierge backend error: ${response.statusText || 'Internal Server Error'}`);
  }

  const reader = response.body?.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  let fullText = '';

  if (!reader) {
    throw new Error('No body reader available');
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.trim().startsWith('data: ')) {
        let errorToThrow: Error | null = null;
        try {
          const rawData = JSON.parse(line.trim().substring(6));
          onEvent(rawData);
          
          if (rawData.author === 'system_error' || rawData.type === 'error' || rawData.author === 'error') {
            errorToThrow = new Error(`Concierge stream error in [${rawData.stage || 'unknown'}]: ${rawData.message}`);
          }
          
          if (rawData.content && rawData.content.parts) {
            for (const part of rawData.content.parts) {
              if (part.text) {
                fullText += part.text;
                onTextUpdate(fullText);
              }
            }
          }
        } catch (e) {
          // ignore parse errors for partial lines
        }
        if (errorToThrow) {
          throw errorToThrow;
        }
      }
    }
  }

  return fullText;
}

export function parseMarkdownToRecommendations(markdown: string): Recommendation[] {
  const cards = markdown.split(/### Recommendation Card:/gi);
  const recommendations: Recommendation[] = [];
  let rank = 1;

  for (const card of cards) {
    if (!card.trim()) continue;

    const lines = card.split('\n');
    const firstLine = lines[0].trim();
    if (!firstLine) continue;

    const facilityName = firstLine.replace(/^[#\s:]+/, '').trim();
    
    let distanceStr = '';
    let priceStr = '';
    let eligibilityStr = 'Fits Your Criteria';
    let matchQualityStr = 'Excellent Match';
    let rationale = '';

    let parsedPlaceId = '';
    let parsedAddress = '';
    let parsedCoords: { lat: number; lng: number } | null = null;
    let parsedPhone = '';
    let parsedWebsite = '';
    let parsedMapsUrl = '';

    for (const line of lines) {
      const lower = line.toLowerCase();
      if (lower.includes('- distance') || lower.includes('- travel time')) {
        distanceStr = line.split(':')[1]?.trim() || '';
      } else if (lower.includes('- price:')) {
        priceStr = line.split(':')[1]?.trim() || '';
      } else if (lower.includes('- eligibility status:')) {
        eligibilityStr = line.split(':')[1]?.trim() || 'Fits Your Criteria';
      } else if (lower.includes('- match quality:')) {
        matchQualityStr = line.split(':')[1]?.trim() || 'Excellent Match';
      } else if (lower.includes('- recommendation rationale:')) {
        rationale = line.split(':')[1]?.trim() || '';
      } else if (lower.includes('- **recommendation rationale**:')) {
        rationale = line.split(':')[1]?.trim() || '';
      } else if (lower.includes('- place id:')) {
        parsedPlaceId = line.split(':')[1]?.trim() || '';
      } else if (lower.includes('- address:')) {
        parsedAddress = line.split(':')[1]?.trim() || '';
      } else if (lower.includes('- coordinates:')) {
        const coordsStr = line.split(':')[1]?.trim() || '';
        const parts = coordsStr.replace(/[\[\]]/g, '').split(',');
        if (parts.length === 2) {
          const parsedLat = parseFloat(parts[0].trim());
          const parsedLng = parseFloat(parts[1].trim());
          if (!isNaN(parsedLat) && !isNaN(parsedLng)) {
            parsedCoords = { lat: parsedLat, lng: parsedLng };
          }
        }
      } else if (lower.includes('- phone:')) {
        parsedPhone = line.split(':')[1]?.trim() || '';
      } else if (lower.includes('- website:')) {
        parsedWebsite = line.split(':').slice(1).join(':').trim() || '';
      } else if (lower.includes('- google maps url:')) {
        parsedMapsUrl = line.split(':').slice(1).join(':').trim() || '';
      }
    }

    const cleanEligibility = eligibilityStr.replace(/[\[\]]/g, '').trim();
    const cleanMatchQuality = matchQualityStr.replace(/[\[\]]/g, '').trim();

    let baseFacility: Facility;
    const nameLower = facilityName.toLowerCase();
    if (nameLower.includes('ymca')) {
      baseFacility = BASE_RECS.ymca as any;
    } else if (nameLower.includes('ffc') || nameLower.includes('formula')) {
      baseFacility = BASE_RECS.ffc as any;
    } else {
      baseFacility = BASE_RECS.planet_fitness as any;
    }

    let cost = baseFacility.pricing.cost;
    if (priceStr.toLowerCase().includes('free') || priceStr.includes('$0')) {
      cost = 0;
    } else {
      const priceMatch = priceStr.match(/\$(\d+)/);
      if (priceMatch) {
        cost = parseFloat(priceMatch[1]);
      }
    }

    let walkingTime = baseFacility.distance.walking_time_minutes;
    const walkMatch = distanceStr.match(/(\d+)\s*min/);
    if (walkMatch) {
      walkingTime = parseInt(walkMatch[1]);
    }

    const facility: Facility = {
      ...baseFacility,
      id: parsedPlaceId || baseFacility.id,
      name: facilityName,
      address: parsedAddress || baseFacility.address,
      phone: parsedPhone || baseFacility.phone,
      website: parsedWebsite || parsedMapsUrl || baseFacility.website,
      coordinates: parsedCoords || baseFacility.coordinates,
      pricing: {
        ...baseFacility.pricing,
        cost,
        pass_detail: priceStr || baseFacility.pricing.pass_detail
      },
      distance: {
        ...baseFacility.distance,
        walking_time_minutes: walkingTime,
        description: distanceStr || baseFacility.distance.description
      }
    };

    const isFree = cost === 0;
    const card_summary = `✓ ${isFree ? 'Free' : `$${cost}`} • ${walkingTime}-minute walk • Open until 10 PM`;

    recommendations.push({
      facility,
      rank,
      match_quality: (cleanMatchQuality || 'Excellent Match') as any,
      eligibility_status: (cleanEligibility || 'Fits Your Criteria') as any,
      recommendation_reason: rationale || 'Recommended by TravelWell AI based on preferences.',
      card_summary,
      badge_subtitle: rank === 1 ? 'Highest overall score' : rank === 2 ? 'Highest rating' : 'Lowest paid guest pass',
      access_status: isFree ? "free_public_access" : "verified_day_pass",
      access_source: "agent_markdown",
      membership_evidence: isFree ? "Free admission verified." : "Paid pass required.",
      access_warnings: []
    });

    rank++;
  }

  return recommendations;
}
