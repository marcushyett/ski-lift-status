/**
 * Zod schemas for ski resort data validation
 * Ensures consistent data format across all platform fetchers
 */

import { z } from 'zod';

/**
 * Status enum for lifts and runs
 */
export const StatusSchema = z.enum(['open', 'closed', 'scheduled']);
export type Status = z.infer<typeof StatusSchema>;

/**
 * Resort information
 */
export const ResortSchema = z.object({
  id: z.string().min(1, 'Resort ID is required'),
  name: z.string().min(1, 'Resort name is required'),
  openskimap_id: z.union([
    z.string().length(40, 'OpenSkiMap ID must be 40 characters'),
    z.array(z.string().length(40, 'OpenSkiMap ID must be 40 characters')).min(1),
  ]),
});
export type Resort = z.infer<typeof ResortSchema>;

/**
 * Lift data structure
 */
export const LiftSchema = z.object({
  // Core fields (required)
  name: z.string().min(1, 'Lift name is required'),
  status: StatusSchema,
  liftType: z.string().min(1, 'Lift type is required'),
  openskimap_ids: z.array(z.string()).default([]),

  // Static metadata (optional)
  capacity: z.number().positive().optional(),
  duration: z.number().positive().optional(),
  length: z.number().positive().optional(),
  uphillCapacity: z.number().positive().optional(),
  speed: z.number().positive().optional(),
  arrivalAltitude: z.number().optional(),
  departureAltitude: z.number().optional(),
  openingTimesTheoretic: z.any().optional(),

  // Real-time data (optional)
  openingTimesReal: z.any().optional(),
  operating: z.boolean().optional(),
  openingStatus: z.string().optional(),
  /**
   * Current queue/waiting time at the lift in minutes.
   * Only available for some resorts. Value of 0 means no wait.
   * @example 5 // 5 minute wait
   */
  waitingTime: z.number().nonnegative().optional(),
  /**
   * Free-text message about the lift status or conditions.
   * Content varies by resort - may include operational notes, restrictions,
   * or safety information. Examples: "Reserved for good skiers",
   * "CLOSED FOR THE (END OF) DAY", "Snowshoes recommended"
   */
  message: z.string().optional(),
});
export type Lift = z.infer<typeof LiftSchema>;

/**
 * Run/Trail data structure
 */
export const RunSchema = z.object({
  // Core fields (required)
  name: z.string().min(1, 'Run name is required'),
  status: StatusSchema,
  trailType: z.string().optional(),
  level: z.string().optional(),
  openskimap_ids: z.array(z.string()).default([]),

  // Static metadata (optional)
  length: z.number().positive().optional(),
  surface: z.union([z.string(), z.number()]).optional(),
  arrivalAltitude: z.number().optional(),
  departureAltitude: z.number().optional(),
  averageSlope: z.number().optional(),
  exposure: z.union([z.string(), z.number()]).optional(),
  guaranteedSnow: z.boolean().optional(),
  openingTimesTheoretic: z.any().optional(),

  // Real-time data (optional)
  openingTimesReal: z.any().optional(),
  operating: z.boolean().optional(),
  openingStatus: z.string().optional(),
  groomingStatus: z.string().optional(),
  snowQuality: z.string().optional(),
  /**
   * Free-text message about the run status or conditions.
   * Content varies by resort - may include partial openings, grooming info,
   * or safety warnings. Examples: "Upper part only", "PARTIE BASSE UNIQUEMENT",
   * "Moguls - expert skiers only"
   */
  message: z.string().optional(),
});
export type Run = z.infer<typeof RunSchema>;

/**
 * Complete resort status response
 */
export const ResortStatusSchema = z.object({
  resort: ResortSchema,
  lifts: z.array(LiftSchema),
  runs: z.array(RunSchema),
});
export type ResortStatus = z.infer<typeof ResortStatusSchema>;

/**
 * Resort configuration
 */
export const ResortConfigSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  openskimap_id: z.union([
    z.string().length(40),
    z.array(z.string().length(40)).min(1),
  ]),
  platform: z.string().min(1),
}).passthrough(); // Allow platform-specific fields

export type ResortConfig = z.infer<typeof ResortConfigSchema>;

/**
 * Fetcher metadata
 */
export const FetcherMetadataSchema = z.object({
  platform: z.string().min(1),
  version: z.string().min(1),
  description: z.string().optional(),
});
export type FetcherMetadata = z.infer<typeof FetcherMetadataSchema>;

/**
 * Validate resort status data
 * Throws ZodError if validation fails with detailed error messages
 */
export function validateResortStatus(data: unknown): ResortStatus {
  return ResortStatusSchema.parse(data);
}

/**
 * Safe validation that returns success/error result
 */
export function safeValidateResortStatus(data: unknown) {
  return ResortStatusSchema.safeParse(data);
}
