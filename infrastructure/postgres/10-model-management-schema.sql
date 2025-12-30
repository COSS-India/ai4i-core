-- ============================================================================
-- Model Management Service Database Schema
-- ============================================================================
-- Creates the model_management_db database and all required tables
-- ============================================================================

-- Create database (will be executed separately if needed)
-- CREATE DATABASE model_management_db WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE_PROVIDER = libc LOCALE = 'en_US.utf8';
-- ALTER DATABASE model_management_db OWNER TO dhruva_user;

-- Connect to model_management_db (this will be handled by the init script)
\c model_management_db

-- Create models table
CREATE TABLE IF NOT EXISTS public.models (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    model_id character varying(255) NOT NULL,
    version character varying(100) NOT NULL,
    submitted_on bigint NOT NULL,
    updated_on bigint NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    ref_url character varying(500),
    task jsonb NOT NULL,
    languages jsonb DEFAULT '[]'::jsonb NOT NULL,
    license character varying(255),
    domain jsonb DEFAULT '[]'::jsonb NOT NULL,
    inference_endpoint jsonb NOT NULL,
    benchmarks jsonb,
    submitter jsonb NOT NULL,
    is_published boolean DEFAULT false NOT NULL,
    published_at bigint,
    unpublished_at bigint,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT models_pkey PRIMARY KEY (id),
    CONSTRAINT models_model_id_key UNIQUE (model_id)
);

ALTER TABLE public.models OWNER TO dhruva_user;

-- Create services table
CREATE TABLE IF NOT EXISTS public.services (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    service_id character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    service_description text,
    hardware_description text,
    published_on bigint NOT NULL,
    model_id character varying(255),
    endpoint character varying(500) NOT NULL,
    api_key character varying(255),
    health_status jsonb,
    benchmarks jsonb,
    is_published boolean DEFAULT false NOT NULL,
    published_at bigint,
    unpublished_at bigint,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT services_pkey PRIMARY KEY (id),
    CONSTRAINT services_service_id_key UNIQUE (service_id),
    CONSTRAINT services_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.models(model_id) ON DELETE CASCADE
);

ALTER TABLE public.services OWNER TO dhruva_user;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_models_model_id ON public.models USING btree (model_id);
CREATE INDEX IF NOT EXISTS idx_services_service_id ON public.services USING btree (service_id);
CREATE INDEX IF NOT EXISTS idx_services_model_id ON public.services USING btree (model_id);

