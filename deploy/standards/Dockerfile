FROM tomcat:10.1.60-jre17-temurin
ARG TDS_SHA256=6bcd23832a44980abebe3dc26ef05bf6216f4215ac8080d2167712b0562f2a81
RUN curl --fail --location --output /usr/local/tomcat/webapps/thredds.war https://downloads.unidata.ucar.edu/tds/5.9/thredds-5.9.war \
    && echo "${TDS_SHA256}  /usr/local/tomcat/webapps/thredds.war" | sha256sum --check \
    && groupadd --gid 10001 ocean && useradd --uid 10001 --gid ocean --create-home ocean \
    && mkdir -p /srv/ocean/content/thredds /srv/ocean/content/data
COPY deploy/standards/catalog.xml deploy/standards/threddsConfig.xml /srv/ocean/content/thredds/
COPY deploy/standards/server.xml /usr/local/tomcat/conf/server.xml
RUN sed -i 's|__OCEAN_DATA__|/srv/ocean/content/data|g' /srv/ocean/content/thredds/catalog.xml \
    && sed -i 's|address="127.0.0.1"|address="0.0.0.0"|g' /usr/local/tomcat/conf/server.xml \
    && chown -R ocean:ocean /srv/ocean /usr/local/tomcat
ENV JAVA_OPTS="-Xms128m -Xmx768m -Djava.awt.headless=true -Dtds.content.root.path=/srv/ocean/content"
USER ocean
EXPOSE 8096
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD curl --fail http://127.0.0.1:8096/thredds/catalog/catalog.xml || exit 1
CMD ["catalina.sh", "run"]
