# Databricks notebook source
# MAGIC %md
# MAGIC # Automotive Data - Cleaning & Transformation (PySpark)
# MAGIC Simple, one-line style transformations using the files in `/Volumes/batch1/raw/ingestion/data/`
# MAGIC
# MAGIC **Files:** `automotive_sales.csv`, `messy_sales.csv`, `vehicle_master.csv`, `dealers.json`, `customer_orders_nested.json`, `service_logs.txt` (pipe separated)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 0. Imports & Path

# COMMAND ----------

from pyspark.sql.functions import *
path = "/Volumes/batch1/raw/ingestion/data/"

# dbutils.fs.ls(path)
display(dbutils.fs.ls(path))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Reading different file types

# COMMAND ----------

# CSV file (header + auto datatype)
df_sales = spark.read.csv(path + "automotive_sales.csv", header=True, inferSchema=True)
df_vehicle = spark.read.csv(path + "vehicle_master.csv", header=True, inferSchema=True)

# Messy CSV - treat the text 'NULL' as real null, keep everything as string first
df_messy = spark.read.option("header", True).option("nullValue", "NULL").csv(path + "messy_sales.csv")

# JSON file (array of objects -> multiLine = True)
df_dealer = spark.read.option("multiLine", True).json(path + "dealers.json")

# Nested JSON file
df_nested = spark.read.option("multiLine", True).json(path + "customer_orders_nested.json")

# Pipe separated text file (no header in file, so we give column names)
df_log = spark.read.csv(path + "service_logs.txt", sep="|", header=False).toDF("log_time","log_level","dealer_id","vehicle_id","message","odometer")

display(df_sales)
df_sales.printSchema()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. select()

# COMMAND ----------

df_sales.select("sale_id","customer_name").display()
df_sales.select(df_sales.sale_id, df_sales.customer_name).display()
df_sales.select(col("sale_id"), col("customer_name")).display()
df_sales.select(df_sales.columns[1:4]).display()
df_sales.select(col("customer_name").alias("cust_name")).display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. withColumn() - basic transformations

# COMMAND ----------

# change datatype
df1 = df_sales.withColumn("quantity", col("quantity").cast("string"))
df1.printSchema()

# arithmetic
df_sales.withColumn("revenue_with_gst", col("revenue") * 1.18).display()
df_sales.withColumn("net_price", col("unit_price") - col("discount")).display()

# constant column
df_sales.withColumn("country", lit("India")).display()

# multiple withColumn chained
df_sales.withColumn("quantity", col("quantity").cast("string")).withColumn("revenue", col("revenue") + 500).withColumn("country", lit("India")).display()

# rename column
df_sales.withColumnRenamed("customer_name","cust_name").display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. filter() / where()

# COMMAND ----------

df_sales.filter(df_sales.state == 'Maharashtra').display()
df_sales.filter((df_sales.state == 'Maharashtra') & (df_sales.revenue > 1000000)).display()
df_sales.filter((df_sales.region == 'North') | (df_sales.region == 'South')).display()
df_sales.filter(df_sales.customer_name.startswith("A")).display()
df_sales.filter(df_sales.customer_name.endswith("Shah")).display()
df_sales.filter(df_sales.customer_name.contains("an")).display()
df_sales.filter(df_sales.customer_name.like("A%Iyer")).display()
df_sales.filter(df_sales.payment_method.isin(["UPI","Card"])).display()
df_sales.filter(~df_sales.payment_method.isin(["UPI","Card"])).display()
df_sales.filter(df_sales.revenue.between(1000000, 2000000)).display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. String operations

# COMMAND ----------

df_sales.withColumn("name_upper", upper(col("customer_name"))).display()
df_sales.withColumn("name_lower", lower(col("customer_name"))).display()
df_sales.withColumn("name_initcap", initcap(col("customer_name"))).display()
df_sales.withColumn("city_trim", trim(col("city"))).display()
df_sales.withColumn("name_length", length(col("customer_name"))).display()
df_sales.withColumn("first3", substring(col("customer_name"), 1, 3)).display()
df_sales.withColumn("full_location", concat(col("city"), lit(" - "), col("state"))).display()
df_sales.withColumn("full_location", concat_ws(" | ", col("city"), col("state"), col("region"))).display()
df_sales.withColumn("first_name", split(col("customer_name"), " ")[0]).withColumn("last_name", split(col("customer_name"), " ")[1]).display()
df_sales.withColumn("email_domain", split(col("customer_email"), "@")[1]).display()
df_sales.withColumn("cust_num", regexp_replace(col("customer_id"), "C", "")).display()
df_sales.withColumn("cust_id_pad", lpad(regexp_replace(col("customer_id"), "C", ""), 6, "0")).display()
df_sales.withColumn("payment_replaced", regexp_replace(col("payment_method"), "UPI", "Online")).display()
df_sales.withColumn("has_gmail", col("customer_email").contains("gmail")).display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 6. Date operations

# COMMAND ----------

df_date = df_sales.withColumn("sale_date", to_date(col("sale_date"))).withColumn("delivery_date", to_date(col("delivery_date")))

df_date.withColumn("sale_year", year(col("sale_date"))).display()
df_date.withColumn("sale_month", month(col("sale_date"))).display()
df_date.withColumn("sale_day", dayofmonth(col("sale_date"))).display()
df_date.withColumn("sale_quarter", quarter(col("sale_date"))).display()
df_date.withColumn("day_of_week", dayofweek(col("sale_date"))).display()
df_date.withColumn("day_name", date_format(col("sale_date"), "EEEE")).display()
df_date.withColumn("month_name", date_format(col("sale_date"), "MMMM")).display()
df_date.withColumn("sale_date_fmt", date_format(col("sale_date"), "dd-MM-yyyy")).display()
df_date.withColumn("delivery_days", datediff(col("delivery_date"), col("sale_date"))).display()
df_date.withColumn("warranty_end", add_months(col("sale_date"), 24)).display()
df_date.withColumn("followup_date", date_add(col("sale_date"), 7)).display()
df_date.withColumn("prev_week", date_sub(col("sale_date"), 7)).display()
df_date.withColumn("today", current_date()).display()
df_date.withColumn("days_since_sale", datediff(current_date(), col("sale_date"))).display()
df_date.withColumn("updated_ts", to_timestamp(col("updated_at"))).withColumn("updated_hour", hour(to_timestamp(col("updated_at")))).display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 7. Cleaning the messy file (`messy_sales.csv`)

# COMMAND ----------

# look at the problems first
display(df_messy)
df_messy.printSchema()   # everything is string because we did not use inferSchema
print(df_messy.count())

# COMMAND ----------

# count of nulls in each column (single line)
df_messy.select([count(when(col(c).isNull(), c)).alias(c) for c in df_messy.columns]).display()

# COMMAND ----------

# STEP 1 - trim + fix text columns
df_clean = df_messy.withColumn("city", initcap(trim(col("city")))).withColumn("state", trim(col("state"))).withColumn("customer_name", initcap(trim(col("customer_name"))))
display(df_clean)

# COMMAND ----------

# STEP 2 - fix datatypes (try_ functions return null instead of error for bad values like 2025-02-30 / not_a_number)
df_clean = df_clean.withColumn("sale_date", expr("try_to_date(sale_date, 'yyyy-MM-dd')")).withColumn("delivery_date", expr("try_to_date(delivery_date, 'yyyy-MM-dd')")).withColumn("updated_at", expr("try_to_timestamp(updated_at)"))
df_clean = df_clean.withColumn("quantity", expr("try_cast(quantity as int)")).withColumn("unit_price", expr("try_cast(unit_price as int)")).withColumn("discount", expr("try_cast(discount as int)")).withColumn("revenue", expr("try_cast(revenue as int)"))
df_clean.printSchema()
display(df_clean)

# COMMAND ----------

# STEP 3 - remove duplicates
print(df_clean.count())
df_clean = df_clean.distinct()                      # full row duplicate
df_clean = df_clean.dropDuplicates(["sale_id"])     # duplicate on key column
print(df_clean.count())

# COMMAND ----------

# STEP 4 - dropna
df_clean.dropna().display()                                          # any column null
df_clean.dropna(how="all").display()                                 # all columns null
df_clean.dropna(subset=["vehicle_id","customer_name"]).display()     # only these columns
df_clean.dropna(thresh=15).display()                                 # keep rows with at least 15 non-null values

# COMMAND ----------

# STEP 5 - fillna
df_clean.fillna(0).display()                                           # all numeric columns
df_clean.fillna("Unknown").display()                                   # all string columns
df_clean.fillna({"discount": 0, "customer_name": "Unknown", "customer_email": "no_email@example.com", "unit_price": 0}).display()

# COMMAND ----------

# STEP 6 - fix wrong values (negative revenue, null vehicle etc.)
df_clean = df_clean.withColumn("revenue", when(col("revenue") < 0, None).otherwise(col("revenue")))
df_clean = df_clean.withColumn("discount", coalesce(col("discount"), lit(0)))
df_clean = df_clean.withColumn("revenue", coalesce(col("revenue"), col("unit_price") * col("quantity") - col("discount")))
df_clean = df_clean.withColumn("delivery_status", when(col("delivery_date").isNull(), "Date Missing").when(col("delivery_date") < col("sale_date"), "Invalid Date").otherwise("OK"))
display(df_clean)

# COMMAND ----------

# STEP 7 - final clean dataframe
df_final = df_clean.dropna(subset=["vehicle_id","sale_date"]).fillna({"customer_name":"Unknown","customer_email":"no_email@example.com","unit_price":0}).withColumnRenamed("customer_name","cust_name")
display(df_final)
print(df_final.count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## 8. when / otherwise (conditional column)

# COMMAND ----------

df_sales.withColumn("price_band", when(col("unit_price") < 1000000, "Low").when(col("unit_price") < 2000000, "Medium").otherwise("High")).display()
df_sales.withColumn("discount_flag", when(col("discount") > 0, "Discount Given").otherwise("No Discount")).display()
df_sales.withColumn("payment_type", when(col("payment_method") == "Finance", "Loan").otherwise("Direct")).display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 9. Sorting & Distinct & Group By

# COMMAND ----------

df_sales.sort(df_sales.revenue.desc()).display()
df_sales.orderBy(df_sales.region.asc(), df_sales.revenue.desc()).display()
df_sales.select("region").distinct().display()
df_sales.dropDuplicates(["city"]).display()

df_sales.groupBy("region").count().display()
df_sales.groupBy("region").sum("revenue").display()
df_sales.groupBy("region").avg("revenue").display()
df_sales.groupBy("region").max("revenue").display()
df_sales.groupBy("region").agg(count("sale_id").alias("total_sales"), sum("revenue").alias("total_revenue"), avg("discount").alias("avg_discount")).display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 10. Vehicle master (`vehicle_master.csv`) - transformations

# COMMAND ----------

display(df_vehicle)
df_vehicle.withColumn("margin", col("base_price") - col("cost_price")).display()
df_vehicle.withColumn("margin_pct", round((col("base_price") - col("cost_price")) / col("base_price") * 100, 2)).display()
df_vehicle.withColumn("vehicle_name", concat_ws(" ", col("brand"), col("model"), col("variant"))).display()
df_vehicle.withColumn("vehicle_age", year(current_date()) - col("model_year")).display()
df_vehicle.withColumn("brand_code", upper(substring(col("brand"), 1, 3))).display()
df_vehicle.filter(df_vehicle.fuel_type.isin(["Petrol","CNG"])).display()
df_vehicle.groupBy("brand").agg(count("*").alias("models"), round(avg("base_price"),0).alias("avg_price")).display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 11. Dealers JSON (`dealers.json`)

# COMMAND ----------

display(df_dealer)
df_dealer.printSchema()
df_dealer.filter(df_dealer.active == True).display()
df_dealer.withColumn("dealer_name", upper(col("dealer_name"))).display()
df_dealer.withColumn("dealer_no", regexp_replace(col("dealer_id"), "D", "").cast("int")).display()
df_dealer.withColumn("manager_no", split(col("manager"), " ")[1]).display()
df_dealer.groupBy("region").count().display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 12. Nested JSON (`customer_orders_nested.json`)

# COMMAND ----------

display(df_nested)
df_nested.printSchema()

# COMMAND ----------

# Struct column -> use dot notation
df_nested.select("customer.customer_id", "customer.name", "customer.address.city", "customer.address.state", "customer.address.postcode").display()

# or flatten with withColumn
df_cust = df_nested.withColumn("customer_id", col("customer.customer_id")).withColumn("name", col("customer.name")).withColumn("city", col("customer.address.city")).withColumn("state", col("customer.address.state")).withColumn("postcode", col("customer.address.postcode")).drop("customer")
display(df_cust)

# COMMAND ----------

# Array column -> explode (customers with empty orders are dropped), explode_outer keeps them
df_nested.select("customer.customer_id", explode("orders").alias("order")).display()
df_nested.select("customer.customer_id", explode_outer("orders").alias("order")).display()

# COMMAND ----------

# Full flatten: struct + array of struct + array of string
df_orders = df_nested.select(col("customer.customer_id").alias("customer_id"), col("customer.name").alias("customer_name"), col("customer.address.city").alias("city"), explode("orders").alias("o"))

df_orders = df_orders.select("customer_id","customer_name","city", col("o.order_id").alias("order_id"), col("o.sale_id").alias("sale_id"), col("o.dealer_id").alias("dealer_id"), col("o.order_date").alias("order_date"), col("o.vehicle.vehicle_id").alias("vehicle_id"), col("o.vehicle.brand").alias("brand"), col("o.vehicle.model").alias("model"), col("o.accessories").alias("accessories"), col("o.payment.method").alias("pay_method"), col("o.payment.amount").alias("pay_amount"), col("o.payment.paid").alias("paid"))
display(df_orders)

# COMMAND ----------

# accessories is an array of strings
df_orders.withColumn("accessory_count", size(col("accessories"))).display()
df_orders.withColumn("accessories_text", array_join(col("accessories"), ", ")).display()
df_orders.withColumn("has_floor_mats", array_contains(col("accessories"), "Floor mats")).display()
df_orders.withColumn("first_accessory", col("accessories")[0]).display()
df_orders.withColumn("accessory", explode(col("accessories"))).display()   # one row per accessory

# date + string on flattened data
df_orders.withColumn("order_date", to_date(col("order_date"))).withColumn("order_month", date_format(col("order_date"), "MMM-yyyy")).withColumn("brand_model", concat_ws(" ", col("brand"), col("model"))).display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 13. Pipe separated file (`service_logs.txt`)

# COMMAND ----------

display(df_log)
df_log.printSchema()

# COMMAND ----------

# clean + datatypes
df_log2 = df_log.withColumn("log_time", to_timestamp(col("log_time"))).withColumn("odometer", col("odometer").cast("int"))
df_log2 = df_log2.withColumn("log_date", to_date(col("log_time"))).withColumn("log_hour", hour(col("log_time"))).withColumn("log_day", date_format(col("log_time"), "EEEE"))
display(df_log2)

# COMMAND ----------

# string operations
df_log2.withColumn("level_lower", lower(col("log_level"))).display()
df_log2.withColumn("dealer_no", regexp_replace(col("dealer_id"), "D", "").cast("int")).display()
df_log2.withColumn("is_brake_issue", col("message").contains("Brake")).display()
df_log2.withColumn("severity", when(col("log_level") == "ERROR", "High").when(col("log_level") == "WARN", "Medium").otherwise("Low")).display()
df_log2.withColumn("odometer_km_k", round(col("odometer") / 1000, 2)).display()

# filters + groupBy
df_log2.filter(df_log2.log_level == "ERROR").display()
df_log2.filter(df_log2.message.like("%sensor%")).display()
df_log2.groupBy("log_level").count().display()
df_log2.groupBy("dealer_id").agg(count("*").alias("total_logs"), max("odometer").alias("max_odometer")).display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 14. Joins (simple)

# COMMAND ----------

# sales + vehicle
df_sales.join(df_vehicle, on="vehicle_id", how="left").display()

# sales + dealer
df_sales.join(df_dealer.select("dealer_id","dealer_name","manager"), on="dealer_id", how="left").display()

# sales + vehicle + dealer in one line
df_join = df_sales.join(df_vehicle, "vehicle_id", "left").join(df_dealer.select("dealer_id","dealer_name","manager"), "dealer_id", "left")
display(df_join)

# service logs + dealer
df_log2.join(df_dealer.select("dealer_id","dealer_name","city"), "dealer_id", "left").display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## 15. Save the cleaned data (dbutils.fs commands)

# COMMAND ----------

# write cleaned data
df_final.write.mode("overwrite").option("header", True).csv(path + "output/clean_sales")
df_join.write.mode("overwrite").parquet(path + "output/sales_joined")
df_orders.drop("accessories").write.mode("overwrite").option("header", True).csv(path + "output/flat_orders")

# dbutils.fs.ls  --> list files and folders
display(dbutils.fs.ls(path + "output/"))

# dbutils.fs.mkdirs --> create directory
# dbutils.fs.mkdirs(path + "archive/")

# dbutils.fs.cp --> copy (copy & paste)
# dbutils.fs.cp(path + "messy_sales.csv", path + "archive/messy_sales.csv")

# dbutils.fs.mv --> move (cut & paste)
# dbutils.fs.mv(path + "archive/messy_sales.csv", path + "archive/messy_sales_old.csv")

# dbutils.fs.rm --> remove file / folder (True = recursive)
# dbutils.fs.rm(path + "output/", True)
