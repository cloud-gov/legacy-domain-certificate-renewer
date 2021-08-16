--
-- PostgreSQL database dump
--

-- Dumped from database version 9.6.18
-- Dumped by pg_dump version 13.3 (Ubuntu 13.3-1.pgdg18.04+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

--
-- Name: alb_proxies; Type: TABLE; Schema: public; Owner: domains_broker
--

CREATE TABLE public.alb_proxies (
    alb_arn text NOT NULL,
    alb_dns_name text,
    listener_arn text
);


ALTER TABLE public.alb_proxies OWNER TO domains_broker;

--
-- Name: certificates; Type: TABLE; Schema: public; Owner: domains_broker
--

CREATE TABLE public.certificates (
    id integer NOT NULL,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    deleted_at timestamp with time zone,
    route_guid text,
    domain text,
    cert_url text,
    certificate bytea,
    arn text,
    name text,
    expires timestamp with time zone
);


ALTER TABLE public.certificates OWNER TO domains_broker;

--
-- Name: certificates_id_seq; Type: SEQUENCE; Schema: public; Owner: domains_broker
--

CREATE SEQUENCE public.certificates_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.certificates_id_seq OWNER TO domains_broker;

--
-- Name: certificates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: domains_broker
--

ALTER SEQUENCE public.certificates_id_seq OWNED BY public.certificates.id;


--
-- Name: routes; Type: TABLE; Schema: public; Owner: domains_broker
--

CREATE TABLE public.routes (
    guid text NOT NULL,
    state text NOT NULL,
    domains text[],
    challenge_json bytea,
    user_data_id integer,
    alb_proxy_arn text
);


ALTER TABLE public.routes OWNER TO domains_broker;

--
-- Name: user_data; Type: TABLE; Schema: public; Owner: domains_broker
--

CREATE TABLE public.user_data (
    id integer NOT NULL,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    deleted_at timestamp with time zone,
    email text NOT NULL,
    reg bytea,
    key bytea
);


ALTER TABLE public.user_data OWNER TO domains_broker;

--
-- Name: user_data_id_seq; Type: SEQUENCE; Schema: public; Owner: domains_broker
--

CREATE SEQUENCE public.user_data_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER TABLE public.user_data_id_seq OWNER TO domains_broker;

--
-- Name: user_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: domains_broker
--

ALTER SEQUENCE public.user_data_id_seq OWNED BY public.user_data.id;


--
-- Name: certificates id; Type: DEFAULT; Schema: public; Owner: domains_broker
--

ALTER TABLE ONLY public.certificates ALTER COLUMN id SET DEFAULT nextval('public.certificates_id_seq'::regclass);


--
-- Name: user_data id; Type: DEFAULT; Schema: public; Owner: domains_broker
--

ALTER TABLE ONLY public.user_data ALTER COLUMN id SET DEFAULT nextval('public.user_data_id_seq'::regclass);


--
-- Name: alb_proxies alb_proxies_pkey; Type: CONSTRAINT; Schema: public; Owner: domains_broker
--

ALTER TABLE ONLY public.alb_proxies
    ADD CONSTRAINT alb_proxies_pkey PRIMARY KEY (alb_arn);


--
-- Name: certificates certificates_pkey; Type: CONSTRAINT; Schema: public; Owner: domains_broker
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_pkey PRIMARY KEY (id);


--
-- Name: routes routes_pkey; Type: CONSTRAINT; Schema: public; Owner: domains_broker
--

ALTER TABLE ONLY public.routes
    ADD CONSTRAINT routes_pkey PRIMARY KEY (guid);


--
-- Name: user_data user_data_pkey; Type: CONSTRAINT; Schema: public; Owner: domains_broker
--

ALTER TABLE ONLY public.user_data
    ADD CONSTRAINT user_data_pkey PRIMARY KEY (id);


--
-- Name: idx_certificates_deleted_at; Type: INDEX; Schema: public; Owner: domains_broker
--

CREATE INDEX idx_certificates_deleted_at ON public.certificates USING btree (deleted_at);


--
-- Name: idx_certificates_expires; Type: INDEX; Schema: public; Owner: domains_broker
--

CREATE INDEX idx_certificates_expires ON public.certificates USING btree (expires);


--
-- Name: idx_routes_state; Type: INDEX; Schema: public; Owner: domains_broker
--

CREATE INDEX idx_routes_state ON public.routes USING btree (state);


--
-- Name: idx_user_data_deleted_at; Type: INDEX; Schema: public; Owner: domains_broker
--

CREATE INDEX idx_user_data_deleted_at ON public.user_data USING btree (deleted_at);


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: domains_broker
--

REVOKE ALL ON SCHEMA public FROM rdsadmin;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO domains_broker;
GRANT ALL ON SCHEMA public TO PUBLIC;


--
-- PostgreSQL database dump complete
--
