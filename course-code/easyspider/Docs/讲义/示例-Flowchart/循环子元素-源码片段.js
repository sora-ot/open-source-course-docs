// 由生成循环子元素演示.py生成；原 Vue 配置与函数按边界从仓库提取。
const demoMessage = {
  "type": "multiCollectWithPattern",
  "history": 1,
  "tabIndex": -1,
  "iframe": false,
  "loopType": 1,
  "xpath": "//div[@class='house']",
  "allXPaths": [
    "//div[@class='house']"
  ],
  "isDescendents": true,
  "parameters": [
    {
      "nodeType": 0,
      "contentType": 1,
      "relative": true,
      "name": "标题",
      "desc": "",
      "relativeXPath": "/h2[1]",
      "allXPaths": [
        "/h2[1]"
      ],
      "exampleValues": [
        {
          "num": 0,
          "value": "海淀单间"
        }
      ],
      "iframe": false
    },
    {
      "nodeType": 0,
      "contentType": 1,
      "relative": true,
      "name": "租金",
      "desc": "",
      "relativeXPath": "/div[1]/span[1]",
      "allXPaths": [
        "/div[1]/span[1]"
      ],
      "exampleValues": [
        {
          "num": 0,
          "value": "2500元"
        }
      ],
      "iframe": false
    }
  ]
};

function DeepClone(obj) {
    if (obj === null || typeof obj !== 'object') return obj;
    let cpObj = obj instanceof Array ? [] : {};
    for (let key in obj) cpObj[key] = DeepClone(obj[key]);
    return cpObj;
}

function newNode(node) {
    id = node["id"];
    title = node["title"];
    type = node["type"];
    if (type == 0) //顺序
    {
        return `<div class="sequence"><div class="node clk" draggable="true" data="${id}" dataType=${type} id = "${id}" position=${node["position"]} pId=${node["parentId"]}>
                <div >
                    <p style="margin-top: 2px">${title}</p>
                </div>
            </div>
            <p class="arrow" draggable="true" position=${node["position"]} data = "${id}" pId=${node["parentId"]}>↓</p></div>`;
    } else if (type == 1) //循环
    {
        return `<div class="loop clk" data="${id}" draggable="true" dataType=${type} id = "${id}" position=${node["position"]} pId=${node["parentId"]}>
             <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">${title}</p>
                <p class="arrow" draggable="true" position=-1 data = "${id}" pId=${id}>↓</p>
            </div>
            <p class="arrow" draggable="true" data = "${id}" position=${node["position"]} pId=${node["parentId"]}>↓</p></div>`;
    } else if (type == 2) //判断
    {
        return LANG(`<div class="loop clk" draggable="true" dataType=${type} data="${id}" position=${node["position"]} pId=${node["parentId"]}>
                    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">${title}</p>
                    <p class="branchAdd" data="${id}">点击此处在最右边增加条件分支</p>
                    <div class="judge" id = "${id}">
                    </div></div>
                    <p class="arrow" draggable="true" data = "${id}" position=${node["position"]} pId=${node["parentId"]}>↓</p></div>`,
            `<div class="loop clk" draggable="true" dataType=${type} data="${id}" position=${node["position"]} pId=${node["parentId"]}>
                    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">${title}</p>
                    <p class="branchAdd" data="${id}">Click here to add a new condition to the right most</p>
                    <div class="judge" id = "${id}">
                    </div></div>
                    <p class="arrow" draggable="true" data = "${id}" position=${node["position"]} pId=${node["parentId"]}>↓</p></div>`);
    } else //判断分支
    {
        return `<div class="branch clk" dataType=${type} data="${id}" position=${node["position"]} pId=${node["parentId"]}>
                    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">${title}</p>
                    <p data = "${id}" class="arrow" draggable="true" position=-1 pId=${id}>↓</p>
                    <div id = "${id}">
                    </div></div>`;
    }
}

function operationChange(e, theNode) {
    try {
        document.getElementById("contextMenu").remove();
    } catch (e) {

    }
    if (nowNode != null) {
        nowNode.style.borderColor = "skyblue";
    }
    nowNode = theNode;
    vueData.nowNodeIndex = actionSequence[theNode.getAttribute("data")];
    theNode.style.borderColor = "blue";
    handleElement(); //处理元素
    if (debuggable && e.button == 0) {
        trialElement(app._data.nowNode, 0);
    } else {
        debuggable = true;
    }
    e.stopPropagation(); //防止冒泡
}

function refresh(nowArrowReset = true) {
    $("#0").empty();
    $("#0").append(`<div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
                        <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
                        </div>
                        <p id="firstArrow" class="arrow" position=-1 pId=0>↓</p>`);
    actionSequence.splice(0);
    queue.splice(0);
    let idd = 1;
    queue.push(0);
    actionSequence.push(0);
    while (queue.length != 0) {
        let nd = queue.shift(); //取出父元素并建立对子元素的链接
        for (let i = 0; i < nodeList[nd].sequence.length; i++) {
            nodeList[nodeList[nd].sequence[i]].parentId = nodeList[nd].id;
            nodeList[nodeList[nd].sequence[i]]["position"] = i;
            nodeList[nodeList[nd].sequence[i]].id = idd++;
            //检测元素是否位于循环内
            if (nodeList[nd].option == 8 || nodeList[nd].isInLoop) {
                nodeList[nodeList[nd].sequence[i]].isInLoop = true;
            } else {
                nodeList[nodeList[nd].sequence[i]].isInLoop = false;
            }
            queue.push(nodeList[nd].sequence[i]);
            actionSequence.push(nodeList[nd].sequence[i]);
        }
    }
    if (nowArrowReset) //如果要重置锚点位置
    {
        app._data.nowArrow = {"position": nodeList[0].sequence.length - 1, "pId": 0, "num": 0}; //设置默认要添加的位置是元素流程最开头处
    }
    //第一个元素不渲染
    for (let i = 1; i < actionSequence.length; i++) {
        let parentId = nodeList[actionSequence[i]]["parentId"];
        $("#" + parentId).append(newNode(nodeList[actionSequence[i]]));
    }
    bindEvents();
}

function deleteElement() {
    if (nowNode == null || nowNode.getAttribute("id") == 0) {
        showError(LANG("当前未选中元素!", "No element is selected now!"));
        return;
    }
    // if (nodeList[actionSequence[nowNode.getAttribute("data")]]["option"] == 1) {
    //     showError("打开网页操作不可删除！");
    //     return;
    // }
    let position = parseInt(nowNode.getAttribute('position'));
    let pId = nowNode.getAttribute('pId');
    let tnode = nodeList[actionSequence[pId]]["sequence"].splice(position, 1); //在相应位置删除元素
    //循环的标记已经被删除的元素，因为删除循环后，循环内的元素也会
    let queue = new Array();
    queue.push(tnode[0]);
    while (queue.length > 0) {
        let index = queue.shift();
        nodeList[index]["id"] = -1; //标记服务已被删除
        for (let i = 0; i < nodeList[index]["sequence"].length; i++) {
            queue.push(nodeList[index]["sequence"][i]);
        }
    }
    app._data["nowNode"] = null;
    app._data["nodeType"] = 0;
    vueData.nowNodeIndex = 0;
    if (nowNode.getAttribute("datatype") == 3) { //如果删掉的是条件分支的话
        pId = nowNode.parentNode.parentNode.getAttribute('pId');
        position = nowNode.parentNode.parentNode.getAttribute('position');
    }
    app.$data.nowArrow = {position: position - 1, "pId": pId, "num": 0}; //删除元素后锚点跳转到当前元素的上一个节点
    refresh(false); //重新渲染页面
    nowNode = null; //取消选择
}

function changeGetDataParameters(msg, i) {
    //Flowchart.js的addParam函数要配套跟上！！！
    msg["parameters"][i]["default"] = ""; //找不到元素时候的默认值
    msg["parameters"][i]["paraType"] = "text"; //参数类型
    msg["parameters"][i]["recordASField"] = 1; //是否记录为字段值
    msg["parameters"][i]["beforeJS"] = ""; //执行前执行的js
    msg["parameters"][i]["beforeJSWaitTime"] = 0; //执行前js等待时间
    msg["parameters"][i]["JS"] = ""; //如果是JS，需要执行的js
    msg["parameters"][i]["JSWaitTime"] = 0; //JS等待时间
    msg["parameters"][i]["afterJS"] = ""; //执行后执行的js
    msg["parameters"][i]["afterJSWaitTime"] = 0; //执行后js等待时间
    msg["parameters"][i]["downloadPic"] = 0; //是否下载图片
    msg["parameters"][i]["splitLine"] = 0; //是否分割行
    try {
        let exampleValue = msg["parameters"][i]["exampleValues"][0]["value"];
        //计算句子中去掉空格后的长度
        let len = exampleValue.replace(/\s+/g, "").length;
        //如果是文本类型的话，长度超过200就默认分割行
        if (len > 200 && msg["parameters"][i]["nodeType"] == 0 && msg["parameters"][i]["contentType"] == 0) {
            msg["parameters"][i]["splitLine"] = 1; //如果示例值长度超过200，就默认分割行
            showInfo(LANG("单个字段示例值长度超过200，已自动开启换行功能。",  "The length of the example value of a single field exceeds 200, and the line break function has been automatically turned on."), 4000);
        }
    } catch (e) {
        console.log(e);
    }
}

function handleElement() {
    app._data["nowNode"] = nodeList[vueData.nowNodeIndex];
    app._data["nodeType"] = app._data["nowNode"]["option"];
    app._data.useLoop = app._data["nowNode"]["parameters"]["useLoop"];
    app._data.xpath = app._data["nowNode"]["parameters"]["xpath"];
    app._data["codeMode"] = -1; //自定义初始化
    if (app._data["nodeType"] == 8) {
        app._data.loopType = app._data["nowNode"]["parameters"]["loopType"];
    } else if (app._data["nodeType"] == 3) {
        app._data.paraIndex = 0; //参数索引初始化
        app._data.params.parameters = app._data["nowNode"]["parameters"]["params"];
    } else if (app._data["nodeType"] == 5) {
        app._data.codeMode = app._data["nowNode"]["parameters"]["codeMode"];
    } else if (app._data["nodeType"] == 10) {
        app._data.TClass = app._data["nowNode"]["parameters"]["class"];
    }
}

function addParameters(t) {
    t["parameters"] = {
        history: 1,
        tabIndex: 0,
        useLoop: false, //是否使用循环中的元素
        xpath: "", //xpath
        iframe: false, //是否在iframe中
        wait: 0, //执行后等待
        waitType: 0, //等待类型，0代表固定时间，1代表随机等待
        beforeJS: "", //执行前执行的js
        beforeJSWaitTime: 0, //执行前js等待时间
        afterJS: "", //执行后执行的js
        afterJSWaitTime: 0, //执行后js等待时间
        waitElement: "", //等待元素
        waitElementTime: 10, //等待元素时间
        waitElementIframeIndex: 0, //等待元素在第几个iframe中
    }; //公共参数处理
    if (t.option == 1) {
        t["parameters"]["url"] = "about:blank";
        t["parameters"]["links"] = "about:blank";
        t["parameters"]["maxWaitTime"] = 10; //最长等待时间
        t["parameters"]["scrollType"] = 0; //滚动类型，0不滚动，1向下滚动1屏，2滚动到底部
        t["parameters"]["scrollCount"] = 1; //滚动次数
        t["parameters"]["scrollWaitTime"] = 1; //滚动后等待时间
        t["parameters"]["cookies"] = ""; //cookies
    } else if (t.option == 2) { //点击元素
        t["parameters"]["scrollType"] = 0; //滚动类型，0不滚动，1向下滚动1屏，2滚动到底部
        t["parameters"]["scrollCount"] = 1; //滚动次数
        t["parameters"]["scrollWaitTime"] = 1; //滚动后等待时间
        t["parameters"]["clickWay"] = 0; //点击方式，0代表selenium点击，1代表js点击
        t["parameters"]["newTab"] = 0; //是否新标签页打开
        t["parameters"]["maxWaitTime"] = 10; //最长等待时间
        t["parameters"]["params"] = []; //默认参数列表
        t["parameters"]["wait"] = 2; //点击后等待时间默认2s
        t["parameters"]["beforeJS"] = ""; //执行前执行的js
        t["parameters"]["beforeJSWaitTime"] = 0; //执行前js等待时间
        t["parameters"]["afterJS"] = ""; //执行后执行的js
        t["parameters"]["afterJSWaitTime"] = 0; //执行后js等待时间
        t["parameters"]["alertHandleType"] = 0; //弹窗处理类型，1代表确认，2代表取消
        t["parameters"]["downloadWaitTime"] = 3600; //下载等待时间
    } else if (t.option == 3) { //提取数据
        t["parameters"]["clear"] = 0; //清空其他字段数据
        t["parameters"]["newLine"] = 1; //生成新行
        t["parameters"]["params"] = []; //默认参数列表
    } else if (t.option == 4) { //输入文字
        t["parameters"]["value"] = "";
        t["parameters"]["index"] = 0; //输入框索引
        t["parameters"]["beforeJS"] = ""; //执行前执行的js
        t["parameters"]["beforeJSWaitTime"] = 0; //执行前js等待时间
        t["parameters"]["afterJS"] = ""; //执行后执行的js
        t["parameters"]["afterJSWaitTime"] = 0; //执行后js等待时间
    } else if (t.option == 5) { //自定义操作
        t["title"] = LANG("执行JavaScript", "Run JavaScript");
        t["parameters"]["clear"] = 0; //清空其他字段数据
        t["parameters"]["newLine"] = 1; //生成新行
        t["parameters"]["codeMode"] = 0; //代码模式，0代表JS, 2代表系统级别
        t["parameters"]["code"] = "";
        t["parameters"]["waitTime"] = 0; //最长等待时间
        t["parameters"]["recordASField"] = 0; //是否记录脚本输出
        t["parameters"]["paraType"] = "text"; //记录脚本输出的字段索引
        t["parameters"]["emailConfig"] = {
            "host": "",
            "port": 465,
            "username": "",
            "password": "",
            "from": "",
            "to": "",
            "subject": "",
            "content": "",
        }
    } else if (t.option == 6) { //切换下拉选项
        t["parameters"]["optionMode"] = 0; //下拉模式
        t["parameters"]["optionValue"] = ""; //下拉值
        t["parameters"]["index"] = 0; //输入框索引
    } else if (t.option == 8) { //循环
        t["title"] = LANG("循环 - 单个元素", "Loop - Single Element");
        t["parameters"]["scrollType"] = 0; //滚动类型，0不滚动，1向下滚动1屏，2滚动到底部
        t["parameters"]["scrollCount"] = 1; //滚动次数
        t["parameters"]["scrollWaitTime"] = 1; //滚动后等待时间
        t["parameters"]["loopType"] = 0; //默认循环类型
        t["parameters"]["xpath"] = "";
        t["parameters"]["pathList"] = "";
        t["parameters"]["textList"] = "";
        t["parameters"]["code"] = ""; //执行的代码
        t["parameters"]["waitTime"] = 0; //最长等待时间
        t["parameters"]["exitCount"] = 0; //执行多少次后退出循环，0代表不设置此条件
        t["parameters"]["exitElement"] = "//body"; //检测此元素不变时退出循环
        t["parameters"]["historyWait"] = 2; //历史记录回退时间，用于循环点击每个链接的情况下点击链接后不打开新标签页的情况
        t["parameters"]["breakMode"] = 0; //break类型，0代表JS，2代表系统命令
        t["parameters"]["breakCode"] = ""; //break条件
        t["parameters"]["breakCodeWaitTime"] = 0; //break条件等待时间
        t["parameters"]["skipCount"] = 0; //跳过前多少次循环
    } else if (t.option == 9) { //条件
        t["title"] = LANG("判断条件 - 从左往右依次判断", "Judgment Condition - Judge from Left to Right");
    } else if (t.option == 10) { //条件分支
        t["parameters"]["class"] = 0; //0代表什么条件都没有，1代表当前页面包括文本，2代表当前页面包括元素，3代表当前循环包括文本，4代表当前循环包括元素
        t["parameters"]["value"] = ""; //相关值
        t["parameters"]["code"] = ""; //code
        t["parameters"]["waitTime"] = 0; //最长等待时间
    }
}

function updateUI() {
    refresh(false);
    app.$data.nowArrow["num"]++; //改变元素的值,通知画图，重新对锚点画图
    let tnodes = document.getElementsByClassName("clk");
    let position = nodeList[vueData.nowNodeIndex]["position"];
    let pid = nodeList[vueData.nowNodeIndex]["parentId"];
    for (let i = 0; i < tnodes.length; i++) {
        if (position == tnodes[i].getAttribute("position") && pid == tnodes[i].getAttribute("pId")) {
            tnodes[i].style.borderColor = "blue"; // 点击了确定按钮之后需要重新对选中的颜色画框
            nowNode = tnodes[i];
            break;
        }
    }
}

function modifyParameters(t, param) {
    t["parameters"]["history"] = param["history"];
    t["parameters"]["tabIndex"] = param["tabIndex"];
    t["parameters"]["iframe"] = param["iframe"];
    if (t.option == 1) {
        t["parameters"]["url"] = param["url"];
        t["parameters"]["links"] = param["links"];
        $("#serviceDescription").val(param["url"]);
        $("#url").val(param["url"]);
    } else if (t.option == 2) { //鼠标点击事件
        t["parameters"]["xpath"] = param["xpath"];
        t["parameters"]["useLoop"] = param["useLoop"];
        t["parameters"]["allXPaths"] = param["allXPaths"];
        if (param["type"] == "loopClickEvery") {
            t["parameters"]["newTab"] = 1; //循环点击每个元素，新标签页打开
        }
    } else if (t.option == 4) { //输入文字事件
        t["parameters"]["value"] = param["value"];
        t["parameters"]["xpath"] = param["xpath"];
        t["parameters"]["allXPaths"] = param["allXPaths"];
        t["parameters"]["useLoop"] = param["useLoop"];
    } else if (t.option == 6) {
        t["parameters"]["xpath"] = param["xpath"];
        t["parameters"]["allXPaths"] = param["allXPaths"];
        t["parameters"]["optionMode"] = param["optionMode"];
        t["parameters"]["optionValue"] = param["optionValue"];
    } else if (t.option == 7) {
        t["parameters"]["xpath"] = param["xpath"];
        t["parameters"]["useLoop"] = param["useLoop"];
        t["parameters"]["allXPaths"] = param["allXPaths"];
    } else if (t.option == 8) { //循环事件
        t["parameters"]["loopType"] = param["loopType"];
        t["parameters"]["xpath"] = param["xpath"];
        t["parameters"]["allXPaths"] = param["allXPaths"];
        t["parameters"]["textList"] = param["value"];
        if (param["nextPage"]) { //循环点击下一页的情况下
            t["title"] = LANG("循环点击下一页", "Loop Click Next Page");
        } else if (param["type"] == "loopClickSingle") { //循环点击单个元素
            t["title"] = LANG("循环点击", "Loop Click");
            let content = param["content"].trim();
            if (content.length > 15) {
                content = content.substring(0, 15) + "...";
                content = LANG("：", ": ") + content;
            } else if (content.length == 0) {
                content = LANG("单个元素", " Single Element");
            } else {
                content = LANG("：", ": ") + content;
            }
            t["title"] += content;
        } else if (param["type"] == "loopClickEvery") { //循环点击每个元素
            t["title"] = LANG("循环点击每个元素", "Loop click Every Element");
        } else if (param["type"] == "loopMouseMove") { //循环移动到单个元素
            t["title"] = LANG("循环移动到每个元素", "Loop Move to Every Element");
        } else if (param["type"] == "multiCollectWithPattern") {
            t["title"] = LANG("循环采集数据", "Loop Collect Data");
        } else if (param["type"] == "batchInputText") {
            t["title"] = LANG("循环输入文字", "Loop Input Text");
        } else {
            t["title"] = LANG("循环", "Loop");
        }
        if (param["loopType"] == 2) //如果是固定元素列表
        {
            t["parameters"]["pathList"] = param["pathList"].join("\n");
        }
    } else if (t.option == 3) { //采集数据
        for (let i = 0; i < param["parameters"].length; i++) {
            changeGetDataParameters(param, i);
        }
        t["parameters"]["params"] = param["parameters"];
    }
}

function updateParentNode() {
    // console.log("updateParentNode")
    let parentNode = nodeList[actionSequence[app._data.nowNode["parentId"]]];
    if (app._data.nowNode.option == 10) { //条件分支的话，传父元素的父元素
        parentNode = nodeList[actionSequence[parentNode["parentId"]]];
    }
    if (parentNode.option == 10) { //如果父元素是条件分支，传父元素的爷爷元素
        parentNode = nodeList[actionSequence[parentNode["parentId"]]];
        parentNode = nodeList[actionSequence[parentNode["parentId"]]];
    }
    app._data.parentNode = parentNode;
}

function trialElement(node, type = 1) {
    // type=0代表标记节点，type=1代表试运行
    // let parentNode = nodeList[actionSequence[node["parentId"]]];
    // if (node.option == 10) { //条件分支的话，传父元素的父元素
    //     parentNode = nodeList[actionSequence[parentNode["parentId"]]];
    // }
    // if (parentNode.option == 10) { //如果父元素是条件分支，传父元素的爷爷元素
    //     parentNode = nodeList[actionSequence[parentNode["parentId"]]];
    //     parentNode = nodeList[actionSequence[parentNode["parentId"]]];
    // }
    updateParentNode();
    let message = {
        type: 4, //消息类型，4代表试运行事件
        from: 1, //0代表从浏览器到流程图，1代表从流程图到浏览器
        message: {"type": type, "node": JSON.stringify(node), "parentNode": JSON.stringify(app._data.parentNode)}
    };
    ws.send(JSON.stringify(message));
    console.log(node);
    console.log(message);
}


// 教学宿主在创建 Vue 前预置完整四节点参数；不复现现场新增的后添加属性时序。
// 参数仍由原 addParameters/modifyParameters 填入。
let nodeList = [], actionSequence = [], queue = [];
let nowNode = null, vueData = {nowNodeIndex: 0};
let id = 0, title = '', type = 0, option = 0, debuggable = true, parameterNum = 3;
function LANG(zh, en) { return zh; }
function inputDelete(event) { event.stopPropagation(); }
let lastDemoMessage = '点击循环或提取节点；在字段表中点“修改”，查看 paraIndex 和原节点参数。';
// 原 trialElement / notifyParameterNum 仍组装消息；本页只记录消息，不发送到外部。
let ws = {send(text) {
  const envelope = JSON.parse(text);
  lastDemoMessage = '原代码组装了 type=' + envelope.type + ' 的消息，本页记录到本地。';
  window.lastTrialEnvelope = envelope;
  syncInspector();
}};
function notifyParameterNum(num) { parameterNum += num; }
function showInfo(text) { lastDemoMessage = text; syncInspector(); }
function showError(text) { showInfo(text); }
function showSuccess(text) { showInfo(text); }
function makeNode(index, nodeTitle, nodeOption, nodeType, sequence) {
  const node = {index, id:0, parentId:0, title:nodeTitle, option:nodeOption,
    type:nodeType, sequence:sequence || [], isInLoop:false};
  addParameters(node);
  return node;
}
nodeList = [makeNode(0,'root',0,-1,[1,2]), makeNode(1,'打开网页',1,0),
  makeNode(2,'循环采集数据',8,1,[3]), makeNode(3,'提取标题和租金',3,0)];
nodeList[0].id = 0;
nodeList[1].parameters.links = 'https://example.com/rent';
modifyParameters(nodeList[2], demoMessage);
modifyParameters(nodeList[3], demoMessage);


let app = new Vue({
    el: '#app',
    data: {
        list: {nl: nodeList},
        index: vueData,
        nodeType: 0, // 当前元素的类型
        nowNode: null, // 用来临时存储元素的节点
        parentNode: null, // 用来临时存储元素的父节点
        codeMode: -1, //代码模式
        loopType: -1, //点击循环时候用来循环选项
        useLoop: false, //记录是否使用循环内元素
        nowArrow: {"position": -1, "pId": 0, "num": 0},
        params: {"parameters": []}, //提取数据的参数列表
        TClass: -1, //条件分支的条件类别
        paraIndex: 0, //当前参数的index
        xpath: "", //当前操作的xpath
        XPaths: "", //xpath列表
    },
    mounted: function () {
        // setTimeout(function () {
        //     $("#flowchart_graph")[0].scrollTo(0, 10000);
        //     window.scrollTo(0, 10000);
        //     console.log("scroll")
        // }, 500);
    },
    // computed: {
    //   finalXPath: function () {
    //       console.log("Call finalXPath")
    //         return this.getFinalXPath(this.nowNode["parameters"]["xpath"], this.nowNode["parameters"]["useLoop"]);
    //   }
    // },
    watch: {
        nowArrow: { //变量发生变化的时候进行一些操作
            deep: true,
            handler: function (newVal, oldVal) {
                let arrlist = document.getElementsByClassName("arrow");
                if (oldVal != null) {
                    for (let i = 0; i < arrlist.length; i++) {
                        if (arrlist[i].getAttribute("position") == oldVal["position"] &&
                            arrlist[i].getAttribute("pid") == oldVal["pId"]) {
                            arrlist[i].style.backgroundColor = ""; // 时刻指示现在应该插入的节点的位置
                            break;
                        }
                    }
                }
                for (let i = 0; i < arrlist.length; i++) {
                    if (arrlist[i].getAttribute("position") == newVal["position"] &&
                        arrlist[i].getAttribute("pid") == newVal["pId"]) {
                        arrlist[i].style.backgroundColor = "lavender"; // 时刻指示现在应该插入的节点的位置
                        break;
                    }
                }
            }
        },
        nowNode: {
            deep: true,
            handler: function (newVal, oldVal) {
                updateUI();
            }
        },
        'nowNode.parameters.xpath': { //xpath发生变化的时候更新参数值
            handler: function (newVal, oldVal) {
                console.log("xpath changed", newVal, oldVal);
            }
        },
        loopType: { //循环类型发生变化的时候更新参数值
            handler: function (newVal, oldVal) {
                // this.nowNode["parameters"]["loopType"] = newVal;
            }
        },
        TClass: {
            handler: function (newVal, oldVal) {
                // this.nowNode["parameters"]["class"] = newVal;
            }
        },
        useLoop: {
            handler: function (newVal, oldVal) {
                this.nowNode["parameters"]["useLoop"] = newVal;
            }
        },
        xpath: {
            handler: function (newVal, oldVal) {
                this.nowNode["parameters"]["xpath"] = newVal;
            }
        },
        params: {
            handler: function (newVal, oldVal) {
                this.nowNode["parameters"]["params"] = newVal["parameters"];
            }
        },
        codeMode: {
            handler: function (newVal, oldVal) {
                // this.nowNode["parameters"]["codeMode"] = newVal;
                // console.log(newVal, oldVal);
                // if (newVal == undefined){
                //     this.codeMode = parseInt(oldVal);
                // }
                // select绑定一定要用:value！！！不然会出现奇怪的问题
            }
        }
    },
    methods: {
        getFinalXPath: function (xpath, useLoop) { //获取最终的xpath
            // console.log(xpath, useLoop, this.parentNode);
            if (this.parentNode == null || this.parentNode.parameters == null || this.parentNode.parameters.xpath == null) {
                return xpath;
            } else if (useLoop) {
                let parent_xpath = this.parentNode.parameters.xpath;
                let final_xpath = "";
                final_xpath = parent_xpath + xpath;
                if (this.parentNode.parameters.loopType == 2) {
                    parent_xpath = this.parentNode.parameters.pathList.split("\n");
                    final_xpath = "";
                    for (let i = 0; i < parent_xpath.length; i++) {
                        final_xpath += parent_xpath[i] + xpath + "\n";
                    }
                }
                return final_xpath;
            } else {
                return xpath;
            }
        },
        handleCodeModeChange: function () {
            // if (this.codeMode == undefined || this.codeMode == null || this.codeMode == -1) {
            //     return;
            // }
            this.nowNode["parameters"]["codeMode"] = this.codeMode;
            // console.log(this.codeMode, value);
            switch (parseInt(this.codeMode)) {
                case 0:
                    this.nowNode["title"] = LANG("执行JavaScript", "Run JavaScript");
                    break;
                case 1:
                    this.nowNode["title"] = LANG("运行操作系统命令", "Run OS Command");
                    break;
                case 2:
                    this.nowNode["title"] = LANG("循环内元素执行JS", "Run JS in Loop");
                    break;
                case 3:
                    this.nowNode["title"] = LANG("退出循环", "Exit Loop");
                    break;
                case 4:
                    this.nowNode["title"] = LANG("跳过当前循环", "Skip Loop");
                    break;
                case 5:
                    this.nowNode["title"] = LANG("执行Python代码", "Exec Python");
                    break;
                case 6:
                    this.nowNode["title"] = LANG("获得Python表达式值", "Eval Python");
                    break;
                case 7:
                    this.nowNode["title"] = LANG("暂停程序", "Pause Task");
                    break;
                case 8:
                    this.nowNode["title"] = LANG("刷新页面", "Refresh Page");
                    break;
                case 9:
                    this.nowNode["title"] = LANG("发送邮件", "Send Email");
                    break;
                case 10:
                    this.nowNode["title"] = LANG("清空字段值", "Clear Field Value");
                    break;
                case 11:
                    this.nowNode["title"] = LANG("生成新行", "Generate New Row");
                    break;
                case 12:
                    this.nowNode["title"] = LANG("退出程序", "Exit Program");
                    break;
                case -1: // 跳转到其他操作时，不改变标题
                    break;
                default: // 默认情况
                    this.nowNode["title"] = LANG("自定义操作", "Custom Action");
                    break;
            }
        },
        handleLoopTypeChange: function () {
            this.nowNode["parameters"]["loopType"] = this.loopType;
            switch (parseInt(this.loopType)) {
                case 0:
                    this.nowNode["title"] = LANG("循环 - 单个元素", "Loop - Single Element");
                    break;
                case 1:
                    this.nowNode["title"] = LANG("循环 - 不固定元素列表", "Loop - Dynamic Element List");
                    break;
                case 2:
                    this.nowNode["title"] = LANG("循环 - 固定元素列表", "Loop - Fixed Element List");
                    break;
                case 3:
                    this.nowNode["title"] = LANG("循环 - 文本列表", "Loop - Text List");
                    break;
                case 4:
                    this.nowNode["title"] = LANG("循环 - 网址列表", "Loop - URL List");
                    break;
                case 5:
                    this.nowNode["title"] = LANG("循环 - JavaScript命令返回值", "Loop - JavaScript Command Return Value");
                    break;
                case 6:
                    this.nowNode["title"] = LANG("循环 - 系统命令返回值", "Loop - OS Command Return Value");
                    break;
                case 7:
                    this.nowNode["title"] = LANG("循环 - Python表达式返回值", "Loop - Python Expression Evaluation Value");
                    break;
                default:
                    this.nowNode["title"] = LANG("循环", "Loop");
                    break;
            }
        },
        handleJudgeTypeChange: function () {
            this.nowNode["parameters"]["class"] = this.TClass;
            switch (parseInt(this.TClass)) {
                case 0:
                    this.nowNode["title"] = LANG("无条件", "No Condition");
                    break;
                case 1:
                    this.nowNode["title"] = LANG("当前页面包含文本", "Current Page Contains Text");
                    break;
                case 2:
                    this.nowNode["title"] = LANG("当前页面包含元素", "Current Page Contains Element");
                    break;
                case 3:
                    this.nowNode["title"] = LANG("当前循环项包含文本", "Current Loop Item Contains Text");
                    break;
                case 4:
                    this.nowNode["title"] = LANG("当前循环项包含元素", "Current Loop Item Contains Element");
                    break;
                case 5:
                    this.nowNode["title"] = LANG("JavaScript命令返回值", "JavaScript Command Return Value");
                    break;
                case 6:
                    this.nowNode["title"] = LANG("系统命令返回值", "OS Command Return Value");
                    break;
                case 7:
                    this.nowNode["title"] = LANG("针对当前循环项的JavaScript命令返回值", "JavaScript Command Return Value for Current Loop Item");
                    break;
                case 8:
                    this.nowNode["title"] = LANG("执行环境下的Python表达式值", "Python Expression Evaluation Value");
                    break;
                default:
                    this.nowNode["title"] = LANG("条件分支", "Condition");
                    break;
            }
        },
        getCookies: function () { //获取cookies
            let command = new WebSocket("ws://localhost:" + getUrlParam("wsport"))
            command.onopen = function () {
                let message = {
                    type: 7, //消息类型，0代表连接操作
                };
                this.send(JSON.stringify(message));
            };
        },
        changeXPaths: function (XPaths) {
            let result = "";
            for (let i = 0; i < XPaths.length; i++) {
                result += XPaths[i] + "\n";
            }
            this.XPaths = result;
        },
        addParam: function () { //添加参数
            this.nowNode["parameters"]["params"].push({
                "nodeType": 0,
                "contentType": 0,
                "relative": false,
                "name": LANG("自定义参数_" + parameterNum.toString(), "Custom_Field_" + parameterNum.toString()),
                "desc": "",
                "iframe": false,
                "extractType": 0,
                "relativeXPath": "//body",
                "recordASField": 1,
                "allXPaths": [],
                "exampleValues": [
                    {
                        "num": 0,
                        "value": LANG("自定义值", "Custom_Value")
                    }
                ],
                "default": "",
                "beforeJS": "",
                "beforeJSWaitTime": 0,
                "JS": "",
                "JSWaitTime": 0,
                "afterJS": "",
                "afterJSWaitTime": 0,
                "downloadPic": 0,
                "paraType": "text",
                "splitLine": 0,
            });
            notifyParameterNum(1);
            this.paraIndex = this.nowNode["parameters"]["params"].length - 1;
            setTimeout(function () {
                $("#app > div.elements > div.toolkitcontain > table.toolkittb4 > tbody > tr:last-child")[0].scrollIntoView(false); //滚动到底部
            }, 200);
        },
        modifyParam: function (i) { //修改第i个参数
            this.paraIndex = i;
            let clone_node = DeepClone(this.nowNode);
            clone_node.option = 11; //单独的提取数据参数节点
            clone_node.parameters.index = i;
            trialElement(clone_node, 0);
        },
        trialParam: function (i) { //试运行第i个参数
            let clone_node = DeepClone(this.nowNode);
            clone_node.option = 11; //单独的提取数据参数节点
            clone_node.parameters.index = i;
            trialElement(clone_node, 1);
        },
        deleteParam: function (i) { //删除第i个参数
            this.nowNode["parameters"]["params"].splice(i, 1);
            //如果参数删除完了，就把提取数据也删掉
            if (this.nowNode["parameters"]["params"].length == 0) {
                deleteElement();
            }
        },
        upParam: function (i) { //上移第i个参数
            if (i != 0) {
                let t = this.nowNode["parameters"]["params"].splice(i, 1)[0];
                this.nowNode["parameters"]["params"].splice(i - 1, 0, t);
            }
        },
        downParam: function (i) { //下移第i个参数
            if (i != this.nowNode["parameters"]["params"].length - 1) {
                let t = this.nowNode["parameters"]["params"].splice(i, 1)[0];
                this.nowNode["parameters"]["params"].splice(i + 1, 0, t);
            }
        },
        getType: function (nodeType, contentType) { //根据类型得到字段名称
            if (contentType == 2) {
                return "InnerHTML";
            } else if (contentType == 3) {
                return "OuterHTML";
            }
            if (nodeType == 2) {
                return LANG("链接地址", "Link Address");
            } else if (nodeType == 1) {
                return LANG("链接文本", "Link Text");
            } else if (nodeType == 4) {
                return LANG("图片地址", "Image Address");
            } else {
                return LANG("文本", "Text");
            }
        }
    }
});


// 以下为教学宿主；原函数、Vue 配置和参数模板在上方保持源码内容。
app.getCookies = function () { showInfo('本页只展示参数状态，不连接浏览器读取 Cookie。'); };
function bindEvents() {
  document.querySelectorAll('#flowchart_graph .clk').forEach(element => {
    element.addEventListener('click', function(event) { operationChange(event, this); });
  });
}
function selectDemoNode(index) {
  const element = document.getElementById(String(nodeList[index].id));
  operationChange({button:0, stopPropagation(){}}, element);
  updateParentNode();
  syncInspector();
}
function syncInspector() {
  const output = document.getElementById('state-output');
  if (!output || typeof app === 'undefined') return;
  const field = app.nodeType === 3 ? app.params.parameters[app.paraIndex] : null;
  output.textContent = JSON.stringify({
    actionSequence:actionSequence.slice(), nowNodeIndex:vueData.nowNodeIndex,
    nodeType:app.nodeType, nowNode:app.nowNode ? 'nodeList['+vueData.nowNodeIndex+']' : null,
    parentNode:app.parentNode ? 'nodeList['+app.parentNode.index+']' : null,
    loopType:app.loopType, paraIndex:app.paraIndex,
    'params.parameters === nodeList[3].parameters.params': app.params.parameters === nodeList[3].parameters.params,
    currentField:field ? {name:field.name, relative:field.relative, relativeXPath:field.relativeXPath,
      contentType:field.contentType, paraType:field.paraType} : null,
    'nodeList[3].parameters':nodeList[3].parameters
  }, null, 2);
  document.getElementById('event-output').textContent = lastDemoMessage;
  document.getElementById('state-summary').textContent =
    'nowNodeIndex=' + vueData.nowNodeIndex + ' → nowNode=nodeList[' + vueData.nowNodeIndex +
    '] → nodeType=' + app.nodeType + '；loopType=' + app.loopType + '；paraIndex=' + app.paraIndex +
    (field ? ' → 当前字段：' + field.name + '，relativeXPath=' + field.relativeXPath : ' → 当前显示循环参数');
}
app.$watch(() => ({nodeType:app.nodeType, node:app.nowNode, parent:app.parentNode,
  paraIndex:app.paraIndex, fields:app.params.parameters}), syncInspector, {deep:true});
document.getElementById('select-loop').onclick = () => selectDemoNode(2);
document.getElementById('select-fields').onclick = () => selectDemoNode(3);
document.getElementById('reset-demo').onclick = () => location.assign(location.pathname);
refresh();
const view = new URLSearchParams(location.search).get('view') || 'title';
// 与“先新增循环并选中，再新增提取并选中”的原交互顺序一致。
selectDemoNode(2);
selectDemoNode(3);
if (view === 'loop') selectDemoNode(2);
if (view === 'rent' || view === 'edited') app.modifyParam(1);
app.$nextTick(() => {
  // 等字段详情切到租金后，通过真正的输入事件检查 v-model 写回。
  if (view === 'edited') {
    const nameInput = document.querySelector('#app .toolkittb4 tr:nth-child(2) input');
    nameInput.value = '月租';
    nameInput.dispatchEvent(new Event('input', {bubbles:true}));
    const pathInput = document.querySelector('#app textarea[placeholder^="如果要写相对"]');
    pathInput.value = '/div[1]/span[@class="rent"]';
    pathInput.dispatchEvent(new Event('input', {bubbles:true}));
  }
  app.$nextTick(() => {
  syncInspector();
  document.body.dataset.ready = '1';
  // 浏览器内核对模板切换、字段共享引用，以及两行网页数据的相对路径。
  const checks = [];
  checks.push(nodeList[2].sequence[0] === 3);
  checks.push(app.nodeType === (view === 'loop' ? 8 : 3));
  if (view !== 'loop') checks.push(app.params.parameters === nodeList[3].parameters.params);
  if (view === 'rent' || view === 'edited') checks.push(app.paraIndex === 1);
  checks.push(app.loopType === 1);
  if (view === 'edited') {
    checks.push(nodeList[3].parameters.params[1].name === '月租');
    checks.push(nodeList[3].parameters.params[1].relativeXPath === '/div[1]/span[@class="rent"]');
  }
  const cards = document.querySelectorAll('#source-page .house');
  const rows = Array.from(cards).map(card => nodeList[3].parameters.params.map(field => {
    const target = document.evaluate('.'+field.relativeXPath, card, null,
      XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
    return Array.from(target.childNodes).filter(n => n.nodeType === Node.TEXT_NODE)
      .map(n => n.textContent.trim()).join('');
  }));
  checks.push(JSON.stringify(rows) === JSON.stringify([['海淀单间','2500元'],['朝阳单间','2800元']]));
  const passed = checks.every(Boolean);
  document.getElementById('verification').textContent = JSON.stringify({passed,view,rows});
  document.body.dataset.verified = passed ? '1' : '0';
  });
});
