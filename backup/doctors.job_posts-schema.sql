/*!40101 SET NAMES binary*/;
/*!40014 SET FOREIGN_KEY_CHECKS=0*/;
/*!40101 SET SQL_MODE='NO_AUTO_VALUE_ON_ZERO,ONLY_FULL_GROUP_BY,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'*/;
/*!40103 SET TIME_ZONE='+00:00' */;
CREATE TABLE `job_posts` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned DEFAULT NULL,
  `cat_id` bigint unsigned DEFAULT NULL,
  `job_title` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `job_details` text COLLATE utf8mb4_unicode_520_ci,
  `city_id` bigint unsigned DEFAULT NULL,
  `job_contract` enum('Fulltime','Parttime','Contractual') COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `salary` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `address` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `email` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `phone` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `opening_hour` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `priority` enum('Urgent','Normal') COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `country_id` bigint unsigned DEFAULT NULL,
  `duration` int DEFAULT NULL,
  `start_date` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `end_date` varchar(255) COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  `status` varchar(255) COLLATE utf8mb4_unicode_520_ci NOT NULL DEFAULT '0',
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  `type` enum('onsite','hybrid','remote') COLLATE utf8mb4_unicode_520_ci DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=6 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_520_ci;
