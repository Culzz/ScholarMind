/** Reference lists used by the filter and profile forms. */

export interface CountryOption {
  iso3: string;
  name: string;
}

/**
 * African countries plus a few common destinations for African students.
 * The corpus is Nigeria-first but the schema is Africa-wide (SRS §11).
 */
export const COUNTRY_OPTIONS: CountryOption[] = [
  { iso3: 'NGA', name: 'Nigeria' },
  { iso3: 'GHA', name: 'Ghana' },
  { iso3: 'KEN', name: 'Kenya' },
  { iso3: 'ZAF', name: 'South Africa' },
  { iso3: 'EGY', name: 'Egypt' },
  { iso3: 'ETH', name: 'Ethiopia' },
  { iso3: 'TZA', name: 'Tanzania' },
  { iso3: 'UGA', name: 'Uganda' },
  { iso3: 'RWA', name: 'Rwanda' },
  { iso3: 'SEN', name: 'Senegal' },
  { iso3: 'CIV', name: "Côte d'Ivoire" },
  { iso3: 'CMR', name: 'Cameroon' },
  { iso3: 'ZWE', name: 'Zimbabwe' },
  { iso3: 'ZMB', name: 'Zambia' },
  { iso3: 'BWA', name: 'Botswana' },
  { iso3: 'NAM', name: 'Namibia' },
  { iso3: 'MOZ', name: 'Mozambique' },
  { iso3: 'AGO', name: 'Angola' },
  { iso3: 'MUS', name: 'Mauritius' },
  { iso3: 'MAR', name: 'Morocco' },
  { iso3: 'DZA', name: 'Algeria' },
  { iso3: 'TUN', name: 'Tunisia' },
  { iso3: 'LBY', name: 'Libya' },
  { iso3: 'SDN', name: 'Sudan' },
  { iso3: 'SOM', name: 'Somalia' },
  { iso3: 'DJI', name: 'Djibouti' },
  { iso3: 'ERI', name: 'Eritrea' },
  { iso3: 'GAB', name: 'Gabon' },
  { iso3: 'GNQ', name: 'Equatorial Guinea' },
  { iso3: 'MDG', name: 'Madagascar' },
  { iso3: 'MLI', name: 'Mali' },
  { iso3: 'BFA', name: 'Burkina Faso' },
  { iso3: 'NER', name: 'Niger' },
  { iso3: 'TCD', name: 'Chad' },
  { iso3: 'MRT', name: 'Mauritania' },
  { iso3: 'GMB', name: 'Gambia' },
  { iso3: 'GNB', name: 'Guinea-Bissau' },
  { iso3: 'STP', name: 'São Tomé and Príncipe' },
  { iso3: 'CPV', name: 'Cabo Verde' },
  { iso3: 'SLE', name: 'Sierra Leone' },
  { iso3: 'LBR', name: 'Liberia' },
  { iso3: 'BEN', name: 'Benin' },
  { iso3: 'TGO', name: 'Togo' },
  { iso3: 'ESH', name: 'Western Sahara' },
  { iso3: 'GBR', name: 'United Kingdom' },
  { iso3: 'USA', name: 'United States' },
  { iso3: 'CAN', name: 'Canada' },
  { iso3: 'AUS', name: 'Australia' },
  { iso3: 'DEU', name: 'Germany' },
  { iso3: 'FRA', name: 'France' },
  { iso3: 'NLD', name: 'Netherlands' },
  { iso3: 'CHN', name: 'China' },
  { iso3: 'JPN', name: 'Japan' },
  { iso3: 'CHE', name: 'Switzerland' },
  { iso3: 'BEL', name: 'Belgium' },
  { iso3: 'SWE', name: 'Sweden' },
];

export const DEGREE_LEVEL_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'bachelors', label: "Bachelor's" },
  { value: 'masters', label: 'Master’s' },
  { value: 'mba', label: 'MBA' },
  { value: 'phd', label: 'PhD' },
  { value: 'postdoc', label: 'Postdoctoral' },
  { value: 'research', label: 'Research' },
];

export const FIELD_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'ENG', label: 'Engineering' },
  { value: 'MED', label: 'Medicine and health' },
  { value: 'BUS', label: 'Business and management' },
  { value: 'LAW', label: 'Law' },
  { value: 'SCI', label: 'Natural sciences' },
  { value: 'SOC', label: 'Social sciences' },
  { value: 'HUM', label: 'Arts and humanities' },
  { value: 'AGR', label: 'Agriculture' },
  { value: 'ICT', label: 'Computing and ICT' },
  { value: 'EDU', label: 'Education' },
];

export const FUNDING_COMPONENT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'tuition', label: 'Tuition' },
  { value: 'stipend', label: 'Stipend' },
  { value: 'travel', label: 'Travel' },
  { value: 'accommodation', label: 'Accommodation' },
  { value: 'insurance', label: 'Insurance' },
];

export const DEADLINE_WINDOW_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'open', label: 'Open now' },
  { value: '30', label: 'Closing within 30 days' },
  { value: '90', label: 'Closing within 90 days' },
  { value: '180', label: 'Closing within 6 months' },
];

export const SORT_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'deadline', label: 'Deadline (soonest first)' },
  { value: 'relevance', label: 'Relevance' },
  { value: 'funding', label: 'Funding coverage confidence' },
  { value: 'verification', label: 'Verification status' },
];
