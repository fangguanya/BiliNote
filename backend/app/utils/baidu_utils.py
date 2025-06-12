from app.utils.logger import get_logger

logger = get_logger(__name__)

def delete_baidu_pan_file(file_path: str, from_request: bool = False) -> bool:
    """
    删除百度网盘文件
    
    :param file_path: 文件路径
    :param from_request: 是否来自用户请求
    :return: 是否删除成功
    """
    try:
        # 使用BaiduPanService删除文件
        from app.services.baidu_pan import BaiduPanService
        baidu_service = BaiduPanService()
        
        # 删除文件
        result = baidu_service.delete_file(file_path)
        
        if result:
            logger.info(f"✅ 百度网盘文件删除成功: {file_path}")
            return True
        else:
            logger.warning(f"⚠️ 百度网盘文件删除失败: {file_path}")
            return False
            
    except Exception as e:
        # 如果是用户请求，则需要记录详细错误
        if from_request:
            logger.error(f"❌ 百度网盘文件删除异常: {file_path}, 错误: {e}")
        else:
            # 非用户请求，只记录简单错误
            logger.warning(f"⚠️ 百度网盘文件删除异常: {file_path}")
            
        return False 