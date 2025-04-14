/*!40101 SET NAMES binary*/;
/*!40014 SET FOREIGN_KEY_CHECKS=0*/;
/*!40101 SET SQL_MODE='NO_AUTO_VALUE_ON_ZERO,ONLY_FULL_GROUP_BY,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'*/;
/*!40103 SET TIME_ZONE='+00:00' */;
CREATE TABLE `wallets` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` bigint unsigned NOT NULL,
  `user_type` varchar(255) COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `currency_id` bigint unsigned NOT NULL,
  `currency_code` varchar(255) COLLATE utf8mb4_unicode_520_ci NOT NULL,
  `balance` decimal(15,2) NOT NULL DEFAULT '0.00',
  `created_at` timestamp NULL DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `wallets_user_id_user_type_currency_id_unique` (`user_id`,`user_type`,`currency_id`),
  KEY `wallets_user_id_user_type_currency_code_index` (`user_id`,`user_type`,`currency_code`)
) ENGINE=InnoDB AUTO_INCREMENT=5808 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_520_ci;
