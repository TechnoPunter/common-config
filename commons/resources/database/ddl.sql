-- public.orders definition

-- Drop table

-- DROP TABLE public.orders;

CREATE TABLE public.orders (
	order_id int4 NOT NULL GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE),
	order_ref varchar NULL,
	model varchar NULL,
	scrip varchar NULL,
	symbol varchar NULL,
	exchange varchar NULL,
	ts int4 NULL,
	order_date varchar NULL,
	o numeric NULL,
	h numeric NULL,
	l numeric NULL,
	c numeric NULL,
	signal int4 NULL,
	sl numeric NULL,
	t1 numeric NULL,
	t2 numeric NULL,
	qty numeric NULL,
	indicators text NULL,
	CONSTRAINT orders_pk PRIMARY KEY (order_id),
	CONSTRAINT orders_un UNIQUE (order_ref)
);



-- public.bt_trade definition

-- Drop table

-- DROP TABLE public.bt_trade;

CREATE TABLE public.bt_trade (
	trade_id int4 NOT NULL GENERATED ALWAYS AS IDENTITY,
	order_ref varchar NULL,
	trade_date varchar NULL,
	price float4 NULL,
	direction varchar NULL,
	qty float4 NULL
);


-- public.bt_trade foreign keys

ALTER TABLE public.bt_trade ADD CONSTRAINT bt_trade_fk FOREIGN KEY (order_ref) REFERENCES public.orders(order_ref) ON DELETE CASCADE ON UPDATE CASCADE;



-- public.broker_trade definition

-- Drop table

-- DROP TABLE public.broker_trade;

CREATE TABLE public.broker_trade (
	trade_id int4 NOT NULL GENERATED ALWAYS AS IDENTITY,
	order_ref varchar NULL,
	trade_date varchar NULL,
	price float4 NULL,
	direction varchar NULL,
	qty float4 NULL,
	remarks varchar NULL
);


-- public.broker_trade foreign keys

ALTER TABLE public.broker_trade ADD CONSTRAINT broker_trade_fk FOREIGN KEY (order_ref) REFERENCES public.orders(order_ref) ON DELETE CASCADE ON UPDATE CASCADE;


-- public.symbol_data definition

-- Drop table

-- DROP TABLE public.symbol_data;

CREATE TABLE public.symbol_data (
	ts int8 NULL,
	symbol varchar NULL,
	timeframe int4 NULL,
	indicator_data text NULL,
	created timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX symbol_data_symbol_index ON public.symbol_data USING btree (symbol);
CREATE INDEX symbol_data_timestamp_symbol_timeframe_index ON public.symbol_data USING btree (ts, symbol, timeframe DESC);


alter table public.training_result add slupdcnt int;

alter table public.training_result add maxprofit float;

alter table public.training_result add maxloss float;

CREATE TABLE public.sl_threshold_range (
	scrip varchar NULL,
	min_target float8 NULL,
	max_target float8 NULL,
	target_step float8 NULL,
	min_sl float8 NULL,
	max_sl float8 NULL,
	sl_step float8 NULL,
	min_trail_sl float8 NULL,
	max_trail_sl float8 NULL,
	trail_sl_step float8 NULL,
	tick float8 NULL,
	CONSTRAINT sl_threshold_range_pk UNIQUE (scrip)
);


CREATE TABLE public.sl_thresholds (
	scrip varchar NULL,
	direction int4 NULL,
	strategy varchar NULL,
	sl float8 NULL,
	trail_sl float8 NULL,
	tick float8 NULL,
	target float8 NULL,
	CONSTRAINT stop_loss_thresholds_pk UNIQUE (scrip, direction, strategy)
);

--ALTER TABLE public.sl_thresholds ADD target float8 NULL;
--ALTER TABLE public.sl_thresholds ADD strategy varchar NULL;



CREATE TABLE public.trades (
	trade_id int4 NOT NULL GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE),
	stat	varchar NULL,
	norenordno	varchar NULL,
	uid	varchar NULL,
	actid	varchar NULL,
	exch	varchar NULL,
	prctyp	varchar NULL,
	ret	varchar NULL,
	s_prdt_ali	varchar NULL,
	prd	varchar NULL,
	flid	varchar NULL,
	fltm	varchar NULL,
	trantype	varchar NULL,
	tsym	varchar NULL,
	qty	varchar NULL,
	token	varchar NULL,
	fillshares	varchar NULL,
	flqty	varchar NULL,
	pp	varchar NULL,
	ls	varchar NULL,
	ti	varchar NULL,
	prc	varchar NULL,
	prcftr	varchar NULL,
	flprc	varchar NULL,
	norentm	varchar NULL,
	exch_tm	varchar NULL,
	exchordid	varchar NULL,
	remarks	varchar NULL
);

CREATE TABLE public.log_store(
	log_id int4 NOT NULL GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 START 1 CACHE 1 NO CYCLE),
	log_key varchar NOT NULL,
	log_type varchar NOT NULL,
	log_data JSONB NOT NULL,
	log_time int4 NOT NULL,
	CONSTRAINT log_store_pk PRIMARY KEY (log_id),
	CONSTRAINT log_store_un UNIQUE (log_key)
);