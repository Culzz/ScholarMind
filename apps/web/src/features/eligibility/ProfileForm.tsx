import { useEffect } from 'react';
import { useForm, type Resolver } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

import { Button } from '@/components/ui/Button';
import {
  COUNTRY_OPTIONS,
  DEGREE_LEVEL_OPTIONS,
  FIELD_OPTIONS,
  FUNDING_COMPONENT_OPTIONS,
} from '@/lib/countries';
import type { DegreeLevel, FundingComponentKind, Profile, ProfileInput } from '@/types/api';

/**
 * Profile schema.
 *
 * Numbers are kept as strings in the form so that an empty input means
 * "not supplied" rather than `0`. A missing fact must stay missing: the
 * eligibility engine turns it into `unknown`, never into a satisfied rule.
 */
const optionalNumber = (label: string, min: number, max: number) =>
  z
    .string()
    .optional()
    .refine(
      (value) =>
        value === undefined ||
        value === '' ||
        (!Number.isNaN(Number(value)) && Number(value) >= min && Number(value) <= max),
      { message: `${label} must be a number between ${min} and ${max}.` },
    );

export const profileSchema = z
  .object({
    nationality_country_iso3: z
      .string()
      .min(3, 'Choose your nationality.')
      .max(3, 'Choose your nationality.'),
    residency_country_iso3: z.string().optional(),
    current_degree_level: z
      .string()
      .min(1, 'Tell us your current degree level.')
      .max(40),
    current_institution: z.string().max(120, 'Keep this under 120 characters.').optional(),
    degree_completion_year: optionalNumber('Graduation year', 1950, 2100),
    age: optionalNumber('Age', 15, 100),
    gpa_value: optionalNumber('Grade', 0, 10),
    gpa_scale: z.string().optional(),
    fields_of_study: z.string().optional(),
    work_experience_months: optionalNumber('Work experience', 0, 600),
    languages: z.string().optional(),
    preferred_destinations: z.string().optional(),
    funding_requirements: z.string().optional(),
    target_intake_year: z
      .string()
      .min(4, 'Enter a target intake year.')
      .max(4, 'Enter a target intake year.'),
  })
  .refine(
    (values) => !values.gpa_value || Boolean(values.gpa_scale),
    {
      message: 'Tell us which scale your grade uses — the funder may state a different one.',
      path: ['gpa_scale'],
    },
  );

export type ProfileFormValues = z.infer<typeof profileSchema>;

const inputClass =
  'block w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-sky-500 focus:outline-none focus:ring-2 focus:ring-sky-500/40';

const labelClass = 'mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600';

const splitList = (value: string | undefined): string[] =>
  (value ?? '')
    .split(',')
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);

const toNumber = (value: string | undefined): number | null => {
  if (value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
};

export function toProfileInput(values: ProfileFormValues): ProfileInput {
  return {
    nationality_country_iso3: values.nationality_country_iso3,
    residency_country_iso3: values.residency_country_iso3 || null,
    current_degree_level: (values.current_degree_level || null) as DegreeLevel | null,
    current_institution: values.current_institution || null,
    degree_completion_year: toNumber(values.degree_completion_year),
    age: toNumber(values.age),
    gpa_value: toNumber(values.gpa_value),
    gpa_scale: values.gpa_scale || null,
    fields_of_study: splitList(values.fields_of_study),
    work_experience_months: toNumber(values.work_experience_months),
    languages: splitList(values.languages).map((entry) => {
      const [code, level = 'unspecified'] = entry.split(':');
      return { code: code.trim(), level: level.trim() };
    }),
    preferred_destinations: splitList(values.preferred_destinations),
    funding_requirements: splitList(values.funding_requirements) as FundingComponentKind[],
    target_intake_year: toNumber(values.target_intake_year) ?? 2027,
  };
}

function profileToFormValues(profile: Profile | undefined): ProfileFormValues {
  return {
    nationality_country_iso3: profile?.nationality_country_iso3 ?? '',
    residency_country_iso3: profile?.residency_country_iso3 ?? '',
    current_degree_level: profile?.current_degree_level ?? '',
    current_institution: profile?.current_institution ?? '',
    degree_completion_year:
      profile?.degree_completion_year === null || profile?.degree_completion_year === undefined
        ? ''
        : String(profile.degree_completion_year),
    age: profile?.age === null || profile?.age === undefined ? '' : String(profile.age),
    gpa_value:
      profile?.gpa_value === null || profile?.gpa_value === undefined ? '' : String(profile.gpa_value),
    gpa_scale: profile?.gpa_scale ?? '',
    fields_of_study: (profile?.fields_of_study ?? []).join(', '),
    work_experience_months:
      profile?.work_experience_months === null || profile?.work_experience_months === undefined
        ? ''
        : String(profile.work_experience_months),
    languages: (profile?.languages ?? []).map((entry) => `${entry.code}:${entry.level}`).join(', '),
    preferred_destinations: (profile?.preferred_destinations ?? []).join(', '),
    funding_requirements: (profile?.funding_requirements ?? []).join(', '),
    target_intake_year: String(profile?.target_intake_year ?? 2027),
  };
}

export interface ProfileFormProps {
  profile?: Profile | undefined;
  onSubmit: (input: ProfileInput) => void | Promise<void>;
  saving?: boolean;
  submitLabel?: string;
  /** Called when the user asks to evaluate with the current answers. */
  onEvaluate?: (input: ProfileInput) => void | Promise<void>;
  evaluating?: boolean;
}

export function ProfileForm({
  profile,
  onSubmit,
  saving = false,
  submitLabel = 'Save profile',
  onEvaluate,
  evaluating = false,
}: ProfileFormProps): JSX.Element {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ProfileFormValues>({
    // The resolver is cast to RHF's `Resolver` shape: the Zod schema's input and
    // output types are identical here (the refinement does not transform values),
    // so this keeps the form fully type-safe without depending on the exact
    // generic arity of the installed resolver package.
    resolver: zodResolver(profileSchema) as unknown as Resolver<ProfileFormValues>,
    defaultValues: profileToFormValues(profile),
    mode: 'onBlur',
  });

  // Keep the form in sync when the profile arrives from the API.
  useEffect(() => {
    reset(profileToFormValues(profile));
  }, [profile, reset]);

  return (
    <form
      onSubmit={handleSubmit((values) => onSubmit(toProfileInput(values)))}
      noValidate
      className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
    >
      <h2 className="text-sm font-semibold text-slate-900">Your profile</h2>
      <p className="mt-1 text-xs text-slate-600">
        Every field you leave blank stays unknown. We never guess a fact on your behalf.
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="nationality" className={labelClass}>
            Nationality *
          </label>
          <select id="nationality" className={inputClass} {...register('nationality_country_iso3')}>
            <option value="">Select…</option>
            {COUNTRY_OPTIONS.map((country) => (
              <option key={country.iso3} value={country.iso3}>
                {country.name}
              </option>
            ))}
          </select>
          {errors.nationality_country_iso3 ? (
            <p className="mt-1 text-xs text-rose-700">{errors.nationality_country_iso3.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="residency" className={labelClass}>
            Country of residence
          </label>
          <select id="residency" className={inputClass} {...register('residency_country_iso3')}>
            <option value="">Not stated</option>
            {COUNTRY_OPTIONS.map((country) => (
              <option key={country.iso3} value={country.iso3}>
                {country.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="degree-level" className={labelClass}>
            Current degree level *
          </label>
          <select id="degree-level" className={inputClass} {...register('current_degree_level')}>
            <option value="">Select…</option>
            {DEGREE_LEVEL_OPTIONS.map((level) => (
              <option key={level.value} value={level.value}>
                {level.label}
              </option>
            ))}
          </select>
          {errors.current_degree_level ? (
            <p className="mt-1 text-xs text-rose-700">{errors.current_degree_level.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="institution" className={labelClass}>
            Current institution
          </label>
          <input
            id="institution"
            type="text"
            className={inputClass}
            placeholder="University of Lagos"
            {...register('current_institution')}
          />
          {errors.current_institution ? (
            <p className="mt-1 text-xs text-rose-700">{errors.current_institution.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="age" className={labelClass}>
            Age
          </label>
          <input id="age" type="number" className={inputClass} {...register('age')} />
          {errors.age ? <p className="mt-1 text-xs text-rose-700">{errors.age.message}</p> : null}
        </div>

        <div>
          <label htmlFor="graduation-year" className={labelClass}>
            Graduation year
          </label>
          <input
            id="graduation-year"
            type="number"
            className={inputClass}
            {...register('degree_completion_year')}
          />
          {errors.degree_completion_year ? (
            <p className="mt-1 text-xs text-rose-700">{errors.degree_completion_year.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="gpa-value" className={labelClass}>
            Grade (as stated on your transcript)
          </label>
          <input id="gpa-value" type="number" step="0.01" className={inputClass} {...register('gpa_value')} />
          {errors.gpa_value ? <p className="mt-1 text-xs text-rose-700">{errors.gpa_value.message}</p> : null}
        </div>

        <div>
          <label htmlFor="gpa-scale" className={labelClass}>
            Grade scale
          </label>
          <select id="gpa-scale" className={inputClass} {...register('gpa_scale')}>
            <option value="">Not stated</option>
            <option value="4">GPA (4.0 scale)</option>
            <option value="5">GPA (5.0 scale)</option>
            <option value="cgpa_4">CGPA (4.0 scale)</option>
            <option value="cgpa_5">CGPA (5.0 scale)</option>
            <option value="percentage">Percentage</option>
            <option value="first_class">First class</option>
            <option value="second_class_upper">Second class upper (2:1)</option>
            <option value="second_class_lower">Second class lower (2:2)</option>
          </select>
          {errors.gpa_scale ? (
            <p className="mt-1 text-xs text-rose-700">{errors.gpa_scale.message}</p>
          ) : null}
        </div>

        <div>
          <label htmlFor="work-experience" className={labelClass}>
            Work experience (months)
          </label>
          <input
            id="work-experience"
            type="number"
            className={inputClass}
            {...register('work_experience_months')}
          />
        </div>

        <div>
          <label htmlFor="target-year" className={labelClass}>
            Target intake year *
          </label>
          <input
            id="target-year"
            type="number"
            className={inputClass}
            {...register('target_intake_year')}
          />
          {errors.target_intake_year ? (
            <p className="mt-1 text-xs text-rose-700">{errors.target_intake_year.message}</p>
          ) : null}
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="fields" className={labelClass}>
            Fields of study (comma separated codes)
          </label>
          <input id="fields" type="text" className={inputClass} placeholder="ENG, ICT" {...register('fields_of_study')} />
          <p className="mt-1 text-xs text-slate-500">
            Available codes: {FIELD_OPTIONS.map((field) => field.value).join(', ')}
          </p>
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="languages" className={labelClass}>
            Languages (format: code:level, comma separated)
          </label>
          <input
            id="languages"
            type="text"
            className={inputClass}
            placeholder="en:advanced, fr:intermediate"
            {...register('languages')}
          />
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="destinations" className={labelClass}>
            Preferred destinations (comma separated country codes)
          </label>
          <input id="destinations" type="text" className={inputClass} placeholder="GBR, CAN" {...register('preferred_destinations')} />
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="funding-requirements" className={labelClass}>
            Funding you consider essential (comma separated)
          </label>
          <input
            id="funding-requirements"
            type="text"
            className={inputClass}
            placeholder="tuition, stipend, travel"
            {...register('funding_requirements')}
          />
          <p className="mt-1 text-xs text-slate-500">
            Available: {FUNDING_COMPONENT_OPTIONS.map((component) => component.value).join(', ')}
          </p>
        </div>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <Button type="submit" loading={saving}>
          {submitLabel}
        </Button>
        {onEvaluate ? (
          <Button
            type="button"
            variant="secondary"
            loading={evaluating}
            onClick={() => void handleSubmit((values) => onEvaluate(toProfileInput(values)))}
          >
            Save and evaluate
          </Button>
        ) : null}
      </div>
    </form>
  );
}

export default ProfileForm;
